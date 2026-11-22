# -*- coding: utf-8 -*-
"""检查器集合。每个检查器是 (doc, pdf_path) -> Iterable[Finding]。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pymupdf

from .core import (
    Finding,
    LINE_END_FORBIDDEN,
    LINE_START_FORBIDDEN,
    RE_ZH,
    TextCache,
    ZH_RANGE,
)

# ---------------------------------------------------------------- 1. 缺字
_NOTDEF_SIGNS = (("\ufffd", "替换符 U+FFFD（疑似缺字）"),
                 ("\u25a1", "□ U+25A1（豆腐块）"))


def check_notdef(doc: pymupdf.Document, pdf_path: Path, limit: int = 50,
                 cache: TextCache | None = None) -> Iterable[Finding]:
    cache = cache or TextCache(doc)
    n = 0
    for pno, page in enumerate(doc, 1):
        text = cache.plain(page)
        for ch, label in _NOTDEF_SIGNS:
            count = text.count(ch)
            if count:
                idx = text.find(ch)
                ctx = text[max(0, idx - 20):idx + 20].replace("\n", "⏎")
                yield Finding("notdef", "error", pno, f"{label} ×{count}", ctx)
                n += 1
                if n >= limit:
                    return


# ---------------------------------------------------------------- 2. 字体嵌入
_FONTFILE_KEYS = ("FontFile", "FontFile2", "FontFile3")
_REF_RE = re.compile(r"(\d+)\s+0\s+R")


def _fontfile_in(doc: pymupdf.Document, xref: int) -> str | None:
    """在 xref 自身或其 FontDescriptor 里找 FontFile*。"""
    sources = [xref]
    fd = doc.xref_get_key(xref, "FontDescriptor")
    if fd and fd[0] == "xref":
        sources.append(int(fd[1].split()[0]))
    for xr in sources:
        for key in _FONTFILE_KEYS:
            v = doc.xref_get_key(xr, key)
            if v and v[0] != "null":
                return key
    return None


def _descendant_fontfiles(doc: pymupdf.Document, xref: int) -> list[str]:
    """Type0 字体：FontFile 藏在 DescendantFonts 里。"""
    out = []
    d = doc.xref_get_key(xref, "DescendantFonts")
    if not d or d[0] != "array":
        return out
    for m in _REF_RE.finditer(d[1]):
        ff = _fontfile_in(doc, int(m.group(1)))
        if ff:
            out.append(ff)
    return out


def check_fonts(doc: pymupdf.Document, pdf_path: Path, limit: int = 50) -> Iterable[Finding]:
    """未嵌入字体。Type0 查 DescendantFonts，Simple 查自身 FontDescriptor。

    注意：`XXX-Identity-H` 形式的 Type0 包装器本身无 FontFile 是正常的，
    嵌入信息在其 descendant 上——不能只看包装器就报未嵌入。
    """
    n = 0
    seen: set[str] = set()
    for xref in range(1, doc.xref_length()):
        t = doc.xref_get_key(xref, "Type")
        if not t or t[1] != "/Font":
            continue
        try:
            base = doc.xref_get_key(xref, "BaseFont")[1] or "?"
            subtype = doc.xref_get_key(xref, "Subtype")
            if subtype and subtype[1] == "/Type0":
                embedded = bool(_descendant_fontfiles(doc, xref))
            else:
                embedded = bool(_fontfile_in(doc, xref))
        except Exception as e:  # 损坏 PDF：单个对象解析失败不拖垮整个检查
            yield Finding("font-not-embedded", "warn", 0,
                          f"字体对象无法解析（文件可能损坏）: xref{xref} ({type(e).__name__})")
            continue
        seen.add(base)
        if base in seen:
            continue
        if not embedded:
            yield Finding("font-not-embedded", "error", 0,
                          f"字体未嵌入: {base}")
            n += 1
            if n >= limit:
                return


# ---------------------------------------------------------------- 3. 禁则
def check_kinsoku(doc: pymupdf.Document, pdf_path: Path, limit: int = 100,
                  cache: TextCache | None = None) -> Iterable[Finding]:
    cache = cache or TextCache(doc)
    n = 0
    for pno, page in enumerate(doc, 1):
        for text in cache.cjk_lines(page):
            if text[0] in LINE_START_FORBIDDEN:
                yield Finding("kinsoku", "warn", pno,
                              f"行首出现避头标点『{text[0]}』", text[:24])
                n += 1
            if text[-1] in LINE_END_FORBIDDEN:
                yield Finding("kinsoku", "warn", pno,
                              f"行尾出现避尾标点『{text[-1]}』", text[-24:])
                n += 1
            if n >= limit:
                return


# ---------------------------------------------------------------- 4. 全半角混排
RE_ZH_EN = re.compile(f"([{ZH_RANGE}])([A-Za-z0-9][A-Za-z0-9\\-\\.]*)")
RE_FW_ALNUM = re.compile(r"[Ａ-Ｚａ-ｚ０-９]+")


def check_mixed_width(doc: pymupdf.Document, pdf_path: Path, limit: int = 100,
                      cache: TextCache | None = None) -> Iterable[Finding]:
    cache = cache or TextCache(doc)
    n = 0
    for pno, page in enumerate(doc, 1):
        text = cache.plain(page)
        for m in RE_ZH_EN.finditer(text):
            ctx = text[max(0, m.start() - 10):m.end() + 10].replace("\n", " ")
            yield Finding("mixed-width", "hint", pno,
                          f"中英文之间无空格『{m.group(0)}』", ctx)
            n += 1
            if n >= limit:
                return
        for m in RE_FW_ALNUM.finditer(text):
            ctx = text[max(0, m.start() - 10):m.end() + 10].replace("\n", " ")
            yield Finding("mixed-width", "hint", pno,
                          f"全角字母/数字『{m.group(0)}』", ctx)
            n += 1
            if n >= limit:
                return


# ---------------------------------------------------------------- 5. 元数据泄漏
_META_KEYS = ("Author", "Creator", "Producer", "Company", "Keywords", "Subject", "Title")


def check_metadata(doc: pymupdf.Document, pdf_path: Path) -> Iterable[Finding]:
    md = doc.metadata or {}
    # Word/Office 痕迹
    creator = (md.get("creator") or "")
    producer = (md.get("producer") or "")
    for label, val in (("生成器", creator), ("转换器", producer)):
        for office in ("Microsoft Word", "Microsoft Office", "PowerPoint",
                       "WPS", "LibreOffice"):
            if office.lower() in val.lower():
                yield Finding("metadata", "hint", 0,
                              f"{label}暴露桌面软件: {val[:60]}")
                break
    # 个人姓名：Author 含 CJK 且与文件名无共同子串时提示（保守，只报非空 Author）
    author = (md.get("author") or "").strip()
    if author:
        yield Finding("metadata", "warn", 0,
                      f"作者字段非空: {author[:60]}", "提交评审版建议清空或匿名")


# ---------------------------------------------------------------- 6. 孤立字尾
def check_orphan_tail(doc: pymupdf.Document, pdf_path: Path, limit: int = 30,
                      cache: TextCache | None = None) -> Iterable[Finding]:
    """段落末行只有单个汉字（孤立字尾）。同块内最后一行文本长度==1 且前一行较长。"""
    cache = cache or TextCache(doc)
    n = 0
    for pno, page in enumerate(doc, 1):
        for block in cache.blocks(page):
            if block.get("type") != 0:
                continue
            lines = ["".join(s["text"] for s in ln.get("spans", [])).strip()
                     for ln in block.get("lines", [])]
            lines = [l for l in lines if l]
            if len(lines) >= 2 and RE_ZH.search(lines[-1]):
                last, prev = lines[-1], lines[-2]
                if len(last) == 1 and len(prev) >= 10:
                    yield Finding("orphan-tail", "warn", pno,
                                  f"段落孤立字尾『{last}』", f"上一行: {prev[-20:]}")
                    n += 1
                    if n >= limit:
                        return


# ---------------------------------------------------------------- 7. 页面尺寸
def check_page_size(doc: pymupdf.Document, pdf_path: Path) -> Iterable[Finding]:
    sizes: dict[str, int] = {}
    for pno, page in enumerate(doc, 1):
        r = page.rect
        key = f"{r.width:.1f}×{r.height:.1f}pt"
        sizes.setdefault(key, []).append(pno) if isinstance(sizes.get(key), list) else sizes.setdefault(key, [pno])
    if len(sizes) > 1:
        main = max(sizes.items(), key=lambda kv: len(kv[1]))
        for size, pages in sorted(sizes.items()):
            if size != main[0]:
                yield Finding("page-size", "warn", pages[0],
                              f"页面尺寸不一致: {size}（{len(pages)} 页）",
                              f"主尺寸 {main[0]}（{len(main[1])} 页）")


CHECKS = {
    "notdef": check_notdef,
    "fonts": check_fonts,
    "kinsoku": check_kinsoku,
    "mixed-width": check_mixed_width,
    "metadata": check_metadata,
    "orphan-tail": check_orphan_tail,
    "page-size": check_page_size,
}
