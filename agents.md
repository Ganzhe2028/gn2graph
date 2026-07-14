# agents.md — gn2graph

## 项目概述

gn2graph 是一个轻量级工具，把 GoodNotes 单页超大 whiteboard 导出的 PDF 切成多个带重叠的 tile 图片，并生成 `metadata.json` 描述每块的全局坐标和重叠关系。

输出交给本地多模态模型手动识别，不内置 VLM 调用。

## 技术栈

- Python 3.10+
- PyMuPDF — PDF 渲染
- Pillow — 图像拼接与切片
- argparse — CLI

无 OpenAI/Anthropic/Google API 依赖。

## 文件结构

```
gn2graph/
├── gn2graph.py           # 主脚本
├── requirements.txt      # 依赖
├── .gitignore            # Git 忽略规则
├── agents.md             # 本文件
├── context.md            # 项目上下文沉淀
├── macos/                # macOS 启动器
│   └── build-gn2graph-app.sh
└── goodnotes-whiteboard-test-materials/
    ├── test-editable.pdf
    ├── test-flatten.pdf
    ├── test-Goodnotes.goodnotes
    └── test-image.jpg
```

## 安装与运行

```bash
cd /Users/mac/New/gn2graph
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python gn2graph.py your-notes.pdf
```

输出目录：

```
tiles/
├── tile_000.jpg
├── tile_001.jpg
├── ...
├── metadata.json
├── prompt.md          # 给 LLM 的提示词模板（CRoC 框架）
└── upload/            # 直接上传给 ChatGPT 的内容
    ├── prompt.md
    └── tile_*.jpg
```

## CLI 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `pdf` | - | 输入 PDF 路径 |
| `-o, --output-dir` | `tiles` | 输出目录 |
| `--tile-height` | `2000` | 每块最大高度（像素） |
| `--overlap` | `0.05` | 块间重叠比例 |
| `--dpi` | `200` | PDF 渲染 DPI |
| `--quality` | `90` | 输出 JPEG 质量 |

## macOS 启动器（可选）

项目提供一个 Spotlight 可启动的 `.app`，避免每次打开终端/Cursor。

```bash
./macos/build-gn2graph-app.sh
```

构建完成后：

- 按 `⌘Space`，输入 `gn2graph`，回车启动，选择 PDF 即可。
- 或把 `gn2graph.app` 拖到 Dock，直接把 PDF 拖到图标上处理。
- 输出目录自动放在 PDF 同级，命名为 `{pdf_name}_tiles`。

`build-gn2graph-app.sh` 把项目路径和 venv Python 路径硬编码进 app，因此不依赖 PATH，也不会污染主脚本。

## 设计原则

1. **极简无冗余**：一个脚本文件完成所有工作，不引入框架、配置系统、日志模块。
2. **纯本地**：不调用任何外部 AI API，避免 key 管理、网络依赖和成本问题。
3. **保留空间关系**：通过垂直拼接多页 + 带重叠切片，让跨 tile/跨页的连接关系至少在一个 tile 中完整可见。
4. **机器可读元数据**：`metadata.json` 包含每块的全局 `global_y` 和 `overlap_*`，方便下游合并识别结果。

## 修改注意事项

- 不要引入 OpenAI/Anthropic/Google 等 API 调用。项目定位为"预处理切片器"。
- 如需支持 `.goodnotes` 原生解析，应作为独立脚本或可选模块，不要污染主流程。
- 保持单文件 CLI 形态，除非功能确实膨胀到必须拆分。
