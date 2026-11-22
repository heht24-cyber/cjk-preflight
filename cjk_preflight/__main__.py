# -*- coding: utf-8 -*-
"""cjk-preflight CLI。

用法:
    cjk-preflight check 论文.pdf [更多.pdf ...]
        [--format pretty|json|sarif] [--checks a,b,c] [--max N] [--quiet]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pymupdf

from . import __version__
from .checks import CHECKS
from .core import LEVELS, Finding, Report, TextCache


@contextmanager
def _muffle_native_stdout():
    """把 MuPDF 打到 C 层 fd 1 的错误信息引到临时文件，只影响检查期间。

    这些消息（损坏 PDF 的 syntax error 等）会让 stdout 里的 JSON 前面
    混进垃圾文本。检查器的异常我们在 run() 里逐项捕获，不会漏掉问题
    本身；这里只是挡住原生层的噪声输出。Windows 上 dup2 同样可用（已
    实测），但管道式 stdout（capture_output）时保守起见失败就放行。
    """
    try:
        saved = os.dup(1)
        tmp = tempfile.TemporaryFile(mode="w+")
        os.dup2(tmp.fileno(), 1)
        try:
            yield
        finally:
            sys.stdout.flush()
            os.dup2(saved, 1)
            os.close(saved)
            tmp.close()
    except OSError:
        yield  # 重定向失败：原样执行（错误只是噪声，不影响功能）

SARIF_RULES = {
    "notdef": ("缺字/豆腐块", "正文出现替换符或豆腐块，表示字体缺字形"),
    "font-not-embedded": ("字体未嵌入", "PDF 字体未嵌入，跨设备显示/打印/归档会出问题"),
    "kinsoku": ("标点禁则违规", "行首出现避头标点或行尾出现避尾标点"),
    "mixed-width": ("全半角混排", "中英文之间无空格或使用了全角字母数字"),
    "metadata": ("元数据泄漏", "文档元数据暴露桌面软件或个人信息"),
    "orphan-tail": ("孤立字尾", "段落末行只有单个汉字"),
    "page-size": ("页面尺寸不一致", "文档内存在多种页面尺寸"),
}


def run(path: str | Path, checks: list[str] | None = None,
        max_per_check: int | None = None, muffle_native: bool = True) -> Report:
    pdf_path = Path(path)

    def _run_all() -> Report:
        doc = pymupdf.open(pdf_path)
        rep = Report(path=str(pdf_path), pages=len(doc))
        cache = TextCache(doc)
        names = list(checks) if checks else list(CHECKS)
        for name in names:
            fn = CHECKS.get(name)
            if fn is None:
                raise SystemExit(f"未知检查: {name}（可选: {', '.join(CHECKS)}）")
            kwargs = {"limit": max_per_check} if max_per_check else {}
            try:
                # 文本型检查器共享同一份缓存；不支持 cache 参数的（fonts 等）自动跳过
                try:
                    rep.findings.extend(fn(doc, pdf_path, cache=cache, **kwargs))
                except TypeError:
                    rep.findings.extend(fn(doc, pdf_path, **kwargs))
            except Exception as e:  # 单项检查崩溃不拖垮整个报告
                rep.findings.append(Finding(
                    "internal", "warn", 0,
                    f"检查 {name} 因文件异常中止（其余检查继续）: {type(e).__name__}: "
                    f"{str(e)[:80]}"))
        doc.close()
        rep.findings.sort(key=lambda f: (LEVELS.index(f.level), f.page, f.check))
        return rep

    if muffle_native:
        with _muffle_native_stdout():
            return _run_all()
    return _run_all()


def _sarif(reports: list[Report]) -> dict:
    results = []
    for ri, rep in enumerate(reports):
        for fi, f in enumerate(rep.findings):
            results.append({
                "ruleId": f.check,
                "level": {"error": "error", "warn": "warning", "hint": "note"}[f.level],
                "message": {"text": f.message + (f"  上下文: {f.context}" if f.context else "")},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": Path(rep.path).name},
                        "region": {"startLine": max(f.page, 1)},
                    }
                }],
            })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "cjk-preflight",
                "informationUri": "https://github.com/example/cjk-preflight",
                "version": __version__,
                "rules": [
                    {"id": rid, "shortDescription": {"text": desc[0]},
                     "fullDescription": {"text": desc[1]}}
                    for rid, desc in SARIF_RULES.items()
                ],
            }},
            "results": results,
        }],
    }


def _print_json(s: str) -> None:
    """输出 JSON。

    两个坑：中文 Windows 控制台默认 GBK 写不进部分字符；MuPDF 的 C 层
    错误会直接打到 fd 1 污染 stdout。后者在 run() 里用 fd 重定向治理，
    这里只需保证 Python 侧写不崩。
    """
    try:
        sys.stdout.write(s + "\n")
        sys.stdout.flush()
    except UnicodeEncodeError:
        sys.stdout.buffer.write((s + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="cjk-preflight",
        description="中文 PDF 提交前检查器：缺字、字体嵌入、标点禁则、全半角混排、元数据、孤立字尾、页面尺寸")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="检查 PDF")
    c.add_argument("pdf", nargs="+")
    c.add_argument("--format", choices=("pretty", "json", "sarif"), default="pretty")
    c.add_argument("--checks", help=f"逗号分隔，可选: {','.join(CHECKS)}")
    c.add_argument("--max", type=int, help="每项检查最多报告条数")
    c.add_argument("--quiet", action="store_true", help="只输出退出码相关摘要")
    args = ap.parse_args(argv)

    checks = args.checks.split(",") if args.checks else None
    try:
        reports = [run(p, checks, args.max) for p in args.pdf]
    except pymupdf.FileDataError as e:
        print(f"无法打开: {e}", file=sys.stderr)
        return 2

    if args.format == "json":
        _print_json(json.dumps([r.to_dict() for r in reports], ensure_ascii=False, indent=2))
    elif args.format == "sarif":
        _print_json(json.dumps(_sarif(reports), ensure_ascii=False, indent=2))
    else:
        for rep in reports:
            if args.quiet:
                n_err = rep.error_count
                n_other = len(rep.findings) - n_err
                status = "FAIL" if n_err else "PASS"
                line = f"{status}  {rep.path}  ({n_err} error / {n_other} warn+hint)"
            else:
                line_head = f"\n{rep.path}  ({rep.pages} 页)"
                if not rep.findings:
                    body = ["  ✓ 全部通过"]
                else:
                    body = ["  " + f.pretty() for f in rep.findings]
                n_err = rep.error_count
                n_other = len(rep.findings) - n_err
                line = line_head + "\n" + "\n".join(body) + \
                       f"\n  —— {n_err} error / {n_other} warn+hint"
            try:
                print(line)
            except UnicodeEncodeError:
                sys.stdout.buffer.write(line.encode("utf-8", errors="replace") + b"\n")
                sys.stdout.buffer.flush()
    return max(r.exit_code() for r in reports)


if __name__ == "__main__":
    sys.exit(main())
