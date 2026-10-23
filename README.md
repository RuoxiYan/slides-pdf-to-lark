# slides-pdf-to-lark

将PDF课件转录为可编辑的飞书文档，保留内容层级、LaTeX公式与图文对应关系。

An agent-assisted workflow for transcribing PDF slides into editable Feishu/Lark Docs.

项目包含转录Skill和独立的图片提取工具。Skill由具备视觉理解能力的AI agent执行，负责内容识别、结构恢复和飞书写入；Python工具负责提取图片与生成图表候选区域，不执行全文转录或文档写入。

## 功能

- **结构保留**：按幻灯片阅读顺序转录标题、正文和多级列表，保留缩进层级。
- **可编辑公式**：结合PDF文本与原页图像识别公式，转写为LaTeX，通过飞书公式元素写入，并核对上下标、分式及运算符。
- **图文对应**：提取原生位图，对矢量或组合图进行局部渲染，插入对应正文位置。
- **表格与代码**：可可靠识别的表格转为可编辑表格，代码保留缩进和换行。
- **已有文档续写**：按指定位置追加内容，保留原有正文；来源页码仅用于本地核验，不额外插入页码标题或整页截图。

## 转录到飞书

### 环境准备

- 支持本地文件读取、Python执行和图像理解的AI agent。
- PDF读取技能，以及[官方lark-cli](https://github.com/larksuite/cli)配套的`lark-doc`、`lark-shared`技能。
- 飞书用户授权和目标文档的编辑权限，配置方法见[lark-cli文档](https://github.com/larksuite/cli)。
- Python 3.9+，图片提取依赖见[requirements.txt](requirements.txt)。

### 安装Skill

将`SKILL.md`、`agents/`、`references/`和`scripts/`复制到agent的技能目录，目录名为`lark-transcribe-slides`。以Codex为例：

```text
~/.codex/skills/lark-transcribe-slides/
├── SKILL.md
├── agents/
├── references/
└── scripts/
```

在项目目录安装Python依赖，并确保agent使用该环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

提供源文件路径和目标文档链接后调用：

```text
使用$lark-transcribe-slides，将/path/to/lecture.pdf转录到<飞书文档链接>末尾，
保留列表层级，公式转为可编辑LaTeX，图片插入对应正文位置。
```

完整流程见[SKILL.md](SKILL.md)。转录包含原页核对、分批写入和回读验证，并非单条命令完成的自动转换。

## 独立提取图片

安装上述Python依赖后运行，无需飞书授权：

```bash
python scripts/extract_slide_figures.py /path/to/lecture.pdf --out work/figures
```

使用`--pages`限定PDF页码，`--out`须为尚不存在的目录：

```bash
python scripts/extract_slide_figures.py /path/to/lecture.pdf --out work/sample --pages 1,2,3
```

| 输出 | 内容 |
| --- | --- |
| `review.html` | 候选图及其页内位置预览 |
| `manifest.json` | 页码、区域坐标、附近文字与源文件校验值 |
| `assets/xref-*` | 原生位图，透明蒙版合成为PNG |
| `assets/p*-f*.png` | 图表区域渲染，保留文字与矢量线条 |
| `page-*-locations.png` | 候选区域的位置标注图 |

检查预览后，可通过`--regions`手动指定幻灯片及图表边界，格式见[图片提取说明](references/figure-extraction.md)。

## 适用范围与限制

- 图片提取基于PDF对象和几何规则，装饰或公式可能被选为候选图。多幻灯片分区优先识别白底横向矩形；非白底、旋转页和密集图文需核对或手动指定边界。
- 提取脚本不含OCR或公式识别模型；完整工作流中的文字识别和LaTeX转写由agent完成。无法可靠识别的公式、表格保留局部图像并标注疑点。
- 转录保留内容与层级，不保证复现原课件的字体、颜色和页面布局。

## 开发

```bash
python -m unittest discover -s tests -v
```

提交问题请附运行环境、命令、错误信息及最小复现样本。分享`manifest.json`前请移除其中的私人路径与课件内容。

## 依赖与参考

- [PyMuPDF](https://github.com/pymupdf/PyMuPDF)：PDF解析、图片提取与渲染。
- [lark-cli](https://github.com/larksuite/cli)：飞书文档读写。
- [PDFFigures 2.0](https://github.com/allenai/pdffigures2)：图形区域检测与组合的设计参考，非运行依赖。

## 许可证

原创代码与文档采用[MIT License](LICENSE)。第三方依赖适用各自许可证，PyMuPDF的AGPL/商业许可见[官方说明](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)。
