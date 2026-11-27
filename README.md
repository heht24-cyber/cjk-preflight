# cjk-preflight

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](pyproject.toml)

**中文 PDF 提交前检查器** —— 在你把 PDF 交出去之前，查出中文排版里最伤的那些问题。

## 谁需要它

- **毕业论文 / 课程报告提交前**：格式审查对字体嵌入、页面规格有硬性要求；打印店打开缺字体的 PDF 会变豆腐块
- **期刊 / 会议投稿前**：字体未嵌入是常见的直接退回理由
- **Word / WPS 转 PDF 后**：实测 Word 转出的 PDF 几乎必然字体未嵌入（见下方压测数据）
- **接收别人的 PDF 时**：3 秒判断这文件在别的电脑上会不会出问题

```bash
# 一行安装（推荐 pipx，或直接 uvx 免安装运行）
pipx install git+https://github.com/heht24-cyber/cjk-preflight.git
# 或: pip install git+https://github.com/heht24-cyber/cjk-preflight.git
# 或免安装试用: uvx --from git+https://github.com/heht24-cyber/cjk-preflight.git cjk-preflight check 论文.pdf

cjk-preflight check 论文.pdf                                 # 检查单个 PDF
cjk-preflight check *.pdf --format sarif > results.sarif     # 批量检查并对接代码扫描 / CI
```

## 它查什么

| 检查 ID | 级别 | 说明 |
|---|---|---|
| `notdef` | error | 缺字/豆腐块：正文出现 U+FFFD 替换符或 □（字体缺字形） |
| `font-not-embedded` | error | 字体未嵌入——投稿、打印、归档跨设备必出问题 |
| `metadata` | warn/hint | 元数据泄漏：作者名、生成器暴露 Word/WPS 等桌面软件 |
| `orphan-tail` | warn | 孤立字尾：段落末行只剩一个汉字 |
| `kinsoku` | warn | 标点禁则：行首出现 。，、」等避头标点，行尾出现 「『（ 等避尾标点 |
| `page-size` | warn | 页面尺寸不一致 |
| `mixed-width` | hint | 全半角混排：中英文之间无空格、全角字母/数字 |

退出码：有 error → 1，否则 0。CI 友好。

## 为什么查"编译产物"而不是源码

textidote、chktex、badness 查 **.tex 源码**；overfull 查英文论文的 PDF 但没有中文检查。
中文文档的问题（豆腐块、禁则、未嵌入字体）只有在**最终 PDF** 上才看得见——模板改了、字体被替换、转换器吞了字，源码检查器一无所知。

### 真实语料验证

对真实课程 PDF 的检查结果：

- **Word/WPS 转出的 PDF：3/3 全部中招「字体未嵌入」**（TimesNewRoman、宋体、微软雅黑、Arial 各变体）
- Word 断行产生行首标点（LaTeX 不会出这种错）
- 元数据里留着作者真名
- LaTeX (XeLaTeX + ctex) 产物：字体全嵌入、禁则零违规——工具不误报

## 输出示例

```
$ cjk-preflight check 知识点整理.pdf
知识点整理.pdf  (2 页)
  [ERROR] p0 font-not-embedded: 字体未嵌入: /TimesNewRoman
  [ERROR] p0 font-not-embedded: 字体未嵌入: /TimesNewRoman,Bold
  [WARN ] p0 metadata: 作者字段非空: Nicorn
  [HINT ] p1 mixed-width: 中英文之间无空格『体50』 …气体50~1000——格…
  —— 4 error / 47 warn+hint
```

**更多真实例子见 [examples/真实示例集.md](examples/真实示例集.md)** —— 6 类来源
（中文学位论文模板指南、Word 转换课件、泰文教材、XeLaTeX 作业、工程图纸、
出版商论文），每个都附完整输出和看点解读，包括「干净文档零误报」和
「纯图形 PDF 安静通过」的反例。

## 技术说明

- 纯 Python，唯一依赖 PyMuPDF ≥1.24，无需 TeX Live / poppler
- 字体嵌入检测走 PDF 对象树：Type0/CID 字体的 FontFile 在 `DescendantFonts[0].FontDescriptor` 里，只看包装字典会误报——本工具按 Subtype 分派，LaTeX 产物零误报
- 全部检查确定性、无网络、无 AI

## 限制

- `mixed-width` 对 LaTeX 数学环境内「中文+变量名」会提示（hint 级，属风格建议）
- 扫描件（纯图片 PDF）抽不出文本层，检查会安静通过——不装 OCR

## 真实世界压力测试

在 **1200 个真实 PDF**（TeX Live 文档库 11240 个中抽样 + 本地课程资料/科研文献：LaTeX 产物、Word/WPS 转换、扫描件、损坏文件、800+ 页教科书）上批量验证：

- **1200/1200 正常完成**：零崩溃、零超时、零坏输出
- 损坏 PDF（坏 xref、zlib 数据损坏）：降级为提示继续检查，不中断
- 中文 Windows GBK 终端：输出自动降级编码，不崩
- 性能：880 页教科书 ~21s；常规文档 <1s

## License

MIT
