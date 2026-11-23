"""数据结构与共享常量。"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

LEVELS = ("error", "warn", "hint")

ZH_RANGE = r"\u4e00-\u9fff\u3400-\u4dbf"
RE_ZH = re.compile(f"[{ZH_RANGE}]")

# 避头：不得出现在行首
LINE_START_FORBIDDEN = ("。，、；：？！）》」』】〉》…—％‰·¨ˇ"
                        ".,;:!?)]}»")
# 避尾：不得出现在行尾
LINE_END_FORBIDDEN = "（《「『【〈“‘([{«"

# 孤立 UTF-16 代理对（真实世界 PDF 的字体名/文本里常见脏数据）
_RE_SURROGATE = re.compile(r"[\ud800-\udfff]")


def sanitize(s: str) -> str:
    """剔除孤立代理对等非法码点，避免 JSON 序列化崩溃。"""
    return _RE_SURROGATE.sub("\ufffd", s)


@dataclass
class Finding:
    check: str
    level: str
    page: int
    message: str
    context: str = ""

    def __post_init__(self):
        self.message = sanitize(self.message)
        self.context = sanitize(self.context)

    def pretty(self) -> str:
        ctx = f"  …{self.context}…" if self.context else ""
        return f"[{self.level.upper():5s}] p{self.page} {self.check}: {self.message}{ctx}"


@dataclass
class Report:
    path: str
    pages: int
    findings: list = field(default_factory=list)

    def __post_init__(self):
        self.path = sanitize(self.path)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.level == "error")

    def exit_code(self) -> int:
        return 1 if self.error_count else 0

    def to_dict(self) -> dict:
        return asdict(self)


def iter_visible_lines(page):
    """产出该页含 CJK 的可见文本行。"""
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line.get("spans", [])).strip()
            if text and RE_ZH.search(text):
                yield text


class TextCache:
    """文档级文本缓存：一页只抽取一次，四个检查器共享。

    大部头 PDF（几百页教科书）上 get_text() 是主要成本，重复抽取
    会让总耗时翻 3-4 倍。
    """

    def __init__(self, doc):
        self._doc = doc
        self._plain: dict[int, str] = {}
        self._dict: dict[int, list] = {}

    def plain(self, page) -> str:
        pno = page.number
        if pno not in self._plain:
            try:
                self._plain[pno] = page.get_text()
            except Exception:
                self._plain[pno] = ""
        return self._plain[pno]

    def blocks(self, page) -> list:
        pno = page.number
        if pno not in self._dict:
            try:
                self._dict[pno] = page.get_text("dict")["blocks"]
            except Exception:
                self._dict[pno] = []
        return self._dict[pno]

    def cjk_lines(self, page):
        """含 CJK 的可见文本行（缓存的 dict 结构派生）。"""
        for block in self.blocks(page):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                text = "".join(s["text"] for s in line.get("spans", [])).strip()
                if text and RE_ZH.search(text):
                    yield text
