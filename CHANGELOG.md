# Changelog

## 0.3.0 · 2026-11-24

**禁则误报治理**（由 lshort-zh-cn 139 页社区标杆文档驱动）：

- 行首 `.sty`/`.cls`/`.bib` 等扩展名折行列表不再报避头违规
- 行首 `...`/`%`/`#` 代码示意行不再报违规
- 行尾括号出现在「描述括号本身」的句子（行内含「括号/定界符」字样）不再报避尾违规
- 修复后 lshort-zh-cn 从 15 条违规降至 2 条（剩余为真违规：行首破折号、行首全角右括号）

验证：1200 个真实 PDF 回归零崩溃；真违规检出无回归（PDE 讲义 4 条、
Word 课件 71 条行首标点全部保留）。

## 0.2.2 · 2026-11-23

- 迁移到 pymupdf 官方 API（消除 fitz 弃用警告）
- README 增加「谁需要它」场景段
- pyproject urls 指向真实仓库

## 0.2.1 · 2026-11-22

**真实世界压力测试修复**（1500 个 PDF，5 个真 bug）：

- 孤立 UTF-16 代理对（脏字体名）→ JSON 崩溃：统一 sanitize
- 损坏 PDF 字体对象解析异常 → 整体崩溃：单对象隔离降级
- 中文 Windows GBK 终端输出崩溃：编码自动降级
- MuPDF C 层错误污染 stdout：fd 级静默
- 单项检查崩溃拖垮全报告：逐项 try/except

性能：TextCache 文档级缓存（一页一抽，四检查器共享），
880 页教科书 45s 超时 → 21s 完成。

## 0.2.0 · 2026-11-22

- 新增检查：metadata（作者名/生成器泄漏）、orphan-tail（孤立字尾）、page-size
- 字体检测纯 Python 化（Type0→DescendantFonts），去 TeX Live 依赖，比 pdffonts 更准
- SARIF 2.1.0 输出
- pip 可安装（pyproject + `cjk-preflight` 命令）

## 0.1.0 · 2026-11-21

首个版本：notdef（缺字/豆腐块）、font-not-embedded、kinsoku（禁则）、
mixed-width（全半角混排）四项检查，CLI 双输出格式。
