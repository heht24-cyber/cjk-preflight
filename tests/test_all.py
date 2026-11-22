# -*- coding: utf-8 -*-
"""端到端测试：合成 PDF 验证全部检查的触发与不误报。

运行: python tests/test_all.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from cjk_preflight.__main__ import main as cli_main, run  # noqa: E402


def make_pdf(path: Path, *, tofu: bool, mixed: bool, kinsoku: bool,
             office_meta: bool, author: str | None) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    parts = []
    if tofu:
        parts.append(("72,90", "Missing \ufffd tofu \u25a1"))
    if mixed:
        parts.append(("72,120", "中文English混排无空格"))
    if kinsoku:
        # 两行：第一行正常，第二行行首放避头标点
        page.insert_text((72, 150), "第一行正常文本内容结束", fontname="china-s")
        page.insert_text((72, 180), "，第二行以标点开头违规", fontname="china-s")
    for xy, text in parts:
        page.insert_text(tuple(float(v) for v in xy.split(",")), text,
                         fontname="china-s")
    doc.set_metadata({
        "creator": "Microsoft Office Word" if office_meta else "XeLaTeX",
        "producer": "MiKTeX",
        "author": author or "",
    })
    doc.save(str(path))
    doc.close()


def case(name: str, expect: dict[str, list[str]], **kw) -> Path:
    """生成一个 PDF 并断言各检查命中指定级别的 message 子串。"""
    tmp = Path(tempfile.mkdtemp())
    pdf = tmp / f"{name}.pdf"
    make_pdf(pdf, **kw)
    rep = run(pdf)
    got: dict[str, list[str]] = {}
    for f in rep.findings:
        got.setdefault(f.check, []).append(f.level)
    for check, levels in expect.items():
        assert check in got, f"[{name}] 期望 {check} 触发，实际: {list(got)}"
        for lv in levels:
            assert lv in got[check], f"[{name}] {check} 期望级别 {lv}，实际 {got[check]}"
    print(f"  PASS {name}: {({k: v for k, v in got.items()})}")
    return pdf


def test_clean_pdf_zero_error():
    """干净的 LaTeX 风格 PDF 不应有 error。"""
    pdf = case("clean", expect={}, tofu=False, mixed=False, kinsoku=False,
               office_meta=False, author=None)
    rep = run(pdf)
    assert rep.error_count == 0, f"干净 PDF 出现 error: {[f for f in rep.findings if f.level=='error']}"
    print("  PASS clean: 0 error")


def test_tofu():
    case("tofu", expect={"notdef": ["error"]}, tofu=True, mixed=False,
         kinsoku=False, office_meta=False, author=None)


def test_mixed():
    case("mixed", expect={"mixed-width": ["hint"]}, tofu=False, mixed=True,
         kinsoku=False, office_meta=False, author=None)


def test_kinsoku():
    case("kinsoku", expect={"kinsoku": ["warn"]}, tofu=False, mixed=False,
         kinsoku=True, office_meta=False, author=None)


def test_metadata():
    case("meta-office", expect={"metadata": ["hint", "warn"]}, tofu=False,
         mixed=False, kinsoku=False, office_meta=True, author="某人")


def test_cli_exit_codes():
    """error → exit 1；干净 → exit 0；JSON 可解析。"""
    bad = case("bad", expect={"notdef": ["error"]}, tofu=True, mixed=True,
               kinsoku=True, office_meta=True, author="x")
    good = case("good", expect={}, tofu=False, mixed=False, kinsoku=False,
                office_meta=False, author=None)
    rc_bad = cli_main(["check", str(bad), "--quiet"])
    rc_good = cli_main(["check", str(good), "--quiet"])
    assert rc_bad == 1, f"bad 期望 exit 1, got {rc_bad}"
    assert rc_good == 0, f"good 期望 exit 0, got {rc_good}"
    print("  PASS cli-exit: 1/0")


def test_json_and_sarif():
    bad = case("bad2", expect={"notdef": ["error"]}, tofu=True, mixed=True,
               kinsoku=True, office_meta=True, author="x")
    out = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "cjk_preflight", "check", str(bad), "--format", "json"],
        capture_output=True, text=True, cwd=str(ROOT), encoding="utf-8", errors="replace")
    data = json.loads(out.stdout)
    assert data[0]["findings"], "JSON 输出为空"
    out = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "cjk_preflight", "check", str(bad), "--format", "sarif"],
        capture_output=True, text=True, cwd=str(ROOT), encoding="utf-8", errors="replace")
    sarif = json.loads(out.stdout)
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"], "SARIF results 为空"
    rules = {r["id"] for r in sarif["runs"][0]["tool"]["driver"]["rules"]}
    assert "notdef" in rules
    print("  PASS json+sarif")


if __name__ == "__main__":
    test_clean_pdf_zero_error()
    test_tofu()
    test_mixed()
    test_kinsoku()
    test_metadata()
    test_cli_exit_codes()
    test_json_and_sarif()
    print("\nALL TESTS PASSED")
