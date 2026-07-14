# gn2graph

把 GoodNotes 单页超大 whiteboard 导出的 PDF，切成适合上传给 LLM/VLM 的 tile 图片。

GoodNotes 的超大 whiteboard 导出为 PDF 后分辨率极高（经常超过 10000 像素宽）。直接整张发给 AI 会被严重 downscale，导致手写细字、连接线和结构关系丢失。gn2graph 把它切成若干高分辨率 tile，保留重叠区域，让跨 tile 的内容至少在一个 tile 里完整可见。

项目本身**不调用任何 AI API**，只做本地预处理。

---

## 安装

```bash
cd /Users/mac/New/gn2graph
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用

### 方式一：命令行

```bash
python gn2graph.py your-notes.pdf
```

输出目录默认在 `./tiles/`，默认按 ChatGPT 反馈采用横向切片。

### 方式二：macOS Spotlight / Dock（推荐）

```bash
./macos/build-gn2graph-app.sh
```

构建完成后：

- `⌘Space` → 输入 `gn2graph` → 回车，选择 PDF。
- 或把 `gn2graph.app` 拖到 Dock，直接把 PDF 拖到图标上处理。

macOS 启动器会输出 `{pdf_name}_tiles/` 到 PDF 同级目录。

---

## 输出目录

```text
your-notes_tiles/
├── left_to_right_00.jpg   # 默认横向切片（或 top_to_bottom_00.jpg 纵向模式）
├── left_to_right_01.jpg
├── ...
├── metadata.json          # 每块的全局坐标和重叠关系
├── prompt.md              # 给 LLM 的提示词模板（CRoC 框架）
├── source_text.txt        # 仅当 PDF 含可搜索文本时生成
└── upload/                # 直接上传给 ChatGPT 的内容
    ├── prompt.md
    ├── left_to_right_*.jpg
    └── your-notes.pdf     # 原 PDF（可 --no-source 关闭）
```

### 给 ChatGPT 用

1. 打开 `upload/` 文件夹。
2. 全选里面的 `prompt.md`、所有 `left_to_right_*.jpg`、原 PDF 和 `source_text.txt`（如有）。
3. 拖到 ChatGPT 对话框上传。
4. 在 ChatGPT 里补充你的具体要求，例如：「重点看 left_to_right_03 的右侧」。

默认的 prompt 会让 ChatGPT 把白板内容整理成**结构化会议纪要 + 待办清单**。

---

## 可调参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `-o, --output-dir` | `tiles` | 输出目录 |
| `--mode` | `horizontal` | 切片方向：`horizontal` 横向 / `vertical` 纵向 |
| `--tile-width` | `2000` | 横向模式下每块最大宽度（像素） |
| `--tile-height` | `2000` | 纵向模式下每块最大高度（像素） |
| `--overlap` | `0.10` | 块间重叠比例 |
| `--dpi` | `300` | PDF 渲染 DPI |
| `--quality` | `90` | 输出 JPEG 质量 |
| `--no-source` | - | 不把原 PDF / 可搜索文本复制到 `upload/` |

示例：

```bash
# 默认横向切片，300 DPI，约 8–13 张 left_to_right_*.jpg
python gn2graph.py your-notes.pdf

# 纵向切片
python gn2graph.py your-notes.pdf --mode vertical

# 更高清、更窄的横向切片
python gn2graph.py your-notes.pdf --dpi 400 --tile-width 1500
```

---

## 项目结构

```text
gn2graph/
├── gn2graph.py                 # 主脚本
├── requirements.txt            # 依赖
├── agents.md                   # Agent 协作约定（比 README 更详细）
├── context.md                  # 项目决策与踩坑记录
├── macos/
│   └── build-gn2graph-app.sh   # macOS 启动器构建脚本
└── goodnotes-whiteboard-test-materials/
    └── ...                     # 测试 PDF
```

更多技术细节和修改注意事项见 [`agents.md`](agents.md)。
