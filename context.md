# context.md — gn2graph 项目上下文

> 本文件沉淀本项目的核心决策、踩坑记录和可复用经验。
> 更新时间：2026-07-14

---

## 1. 问题背景

用户核心需求：**识别 GoodNotes 单页超大 whiteboard 导出的 PDF**。

不是多页 PDF 的「跨页」问题，而是单页 whiteboard 画布导出为 PDF 后尺寸极大（例如 10970×4373 像素），直接喂给 AI 时会被严重 downscale，导致：
- 手写细字看不清
- 远距离的连接线/箭头丢失
- 结构关系断裂

## 2. 关键决策

### 2.1 采用 tiling（切片）而非整图缩放

直接缩小整图会丢失细节。默认采用横向切片（`left_to_right_*.jpg`），同时保留纵向切片（`top_to_bottom_*.jpg`）可选。两种方向都带重叠，确保：
- 每个 tile 保持较高分辨率
- 跨 tile 的节点和连接至少在一个 tile 中完整可见
- 相邻 tile 之间有重叠带，方便后续合并识别结果

### 2.2 从「内置 VLM」退到「纯本地切片器」

初始版本调用了 OpenAI API 做识别。后根据用户要求，**去掉所有 VLM/API 调用**，只保留 PDF 渲染 → 拼接 → 切片 → 保存图片 + metadata。

原因：
- 用户希望用本地多模态模型手动处理
- 避免 key 依赖和成本
- 职责更清晰：gn2graph 只做预处理

### 2.3 先处理 PDF，暂时不做 `.goodnotes` 原生解析

虽然调研发现 `franzthiemann/goodparse` 已能部分解析 `.goodnotes` 矢量笔画，但：
- 只支持 strokes，不支持图片、PDF 背景、文本框、橡皮擦
- 格式随 GoodNotes 版本变化，维护成本高
- PDF 导出是稳定、可复现的输入

结论：**PDF 路线作为 MVP，.goodnotes 原生解析作为远期可选项。**

### 2.4 增加 macOS 启动器以降低使用摩擦

早期每次使用都要打开终端/Cursor 输入命令，不符合 macOS 直觉。后增加 `macos/build-gn2graph-app.sh`，用 `osacompile` 编译出一个 AppleScript droplet `.app`：

- 支持 Spotlight 启动（⌘Space → `gn2graph`）
- 支持把 PDF 拖到 Dock icon 处理
- 双击启动时弹出文件选择框
- 输出目录自动放在 PDF 同级，命名为 `{pdf_name}_tiles`

app 内部硬编码项目路径和 venv Python 路径，不依赖 PATH。

### 2.5 增加 prompt 工程层：自动生成 `prompt.md` 和 `upload/`

切片器不能只输出 raw tiles，否则 LLM 不知道这些图是什么、要怎么处理。后增加自动生成 `prompt.md`：

- 采用 CRoC 框架：Context / Request / Output Format / Constraints / Checkpoint
- 默认 Request 为「把白板内容整理成结构化会议纪要 + 待办清单」
- 预留「User's additional request」区块，用户可在 ChatGPT 对话框里补充具体要求
- 同时生成 `upload/` 子目录，内含 `prompt.md` + 所有 tile 图片 + 原 PDF + 可选 `source_text.txt`，可直接全选上传 ChatGPT

这样用户跑完工具后，不需要再打开编辑器写 prompt，打开 `upload/` 全选上传即可。

### 2.6 附带原 PDF 与可搜索文本

根据 ChatGPT 反馈，上传切片图时同时附带原 PDF 和 GoodNotes 导出的可搜索文本/OCR 草稿，能显著提升辨字准确率。实现方式：

- 默认把原 PDF 复制到 `upload/`，方便模型核对全局版面。
- 用 PyMuPDF 抽取 PDF 内嵌文本（非 OCR API），生成 `source_text.txt`；如果 PDF 没有可搜索文本层，则跳过。
- 加 `--no-source` 可在不需要时关闭。

---

## 3. 实现细节

### 3.1 渲染

- 使用 PyMuPDF (`fitz`)
- 默认 300 DPI（可设 400 DPI）
- 渲染后按最大宽度统一，再做垂直拼接

### 3.2 拼接

- 多页 PDF 先垂直拼接成一张长图
- 相邻页面之间用 Pillow 的 `linear_gradient` mask 做羽化重叠
- 重叠比例由 `--overlap` 控制（默认 10%）

### 3.3 切片

- 默认按 `--tile-width`（默认 2000px）横向切成若干列，输出 `left_to_right_*.jpg`
- 纵向模式按 `--tile-height`（默认 2000px）切成若干行，输出 `top_to_bottom_*.jpg`
- tile 之间同样保留 `--overlap` 比例的重叠
- 不足一个 tile 宽/高度的尾部也单独保存

### 3.4 metadata.json

包含关键字段：
- `canvas_size`：原始画布尺寸
- `tile_count`：tile 数量
- 横向模式：`tiles[].global_x` / `global_x_end` + `overlap_left` / `overlap_right`
- 纵向模式：`tiles[].global_y` / `global_y_end` + `overlap_top` / `overlap_bottom`

下游合并识别结果时，可以用对应的全局坐标把各 tile 的相对 bbox 转成全局坐标。

### 3.5 prompt.md 与 upload/

每次运行会在输出目录生成：

- `prompt.md`：给 LLM 的提示词模板（CRoC 框架）
- `upload/`：直接上传给 ChatGPT 的内容
  - `prompt.md`（副本）
  - 所有 `left_to_right_*.jpg` / `top_to_bottom_*.jpg`
  - 原 PDF（默认附带，可用 `--no-source` 关闭）
  - `source_text.txt`（仅当 PDF 含可搜索文本时）

`upload/` 里不放 `metadata.json`，因为关键坐标信息已经写进 `prompt.md` 的 Context 段。

### 3.6 原 PDF 与可搜索文本

- 原 PDF 默认复制到 `upload/`，文件名不变。
- 用 `fitz` 的 `get_text()` 逐页抽取文本；只抽取 PDF 内嵌的可搜索文本层，不调用外部 OCR。
- 抽到的文本写入 `source_text.txt`，并复制到 `upload/`。
- `--no-source` 可关闭这一行为。

---

## 4. 测试结果

测试材料：`goodnotes-whiteboard-test-materials/test-editable.pdf`

- 原始画布：10970×4373 px
- 旧默认（纵向）：tile-height=2000，overlap=5%，输出 3 个 tile
- 新默认（横向，300 DPI，tile-width=2000，overlap=10%）：画布放大到 16455×6559 px，输出 10 个 `left_to_right_*.jpg`

**重要发现**：原图中一条从 `Loop Eng.` 向右下方大弧度延伸到 `学术 / 原理层面的理解` 的青色长弧线，在纵向切片后完整保留在 tile_001 中。这说明 tiling 方案能有效保留远距离连接关系，避免整图 downscale 导致的细线丢失。

人工精读识别结果见：项目内 `gn2graph-output.md`（按旧版 `prompt-legacy.md` 生成的 5 部分报告）和 `graph-manual.json`。

---

## 5. 踩坑与经验

### 5.1 不要混淆「单页超大 whiteboard」和「多页 PDF」

早期曾误以为用户要解决多页 PDF 的跨页连接问题。实际上用户要的是**单页超大画布**被 AI 切片后的识别问题。后续沟通中已纠正。

### 5.2 不需要复杂图像拼接算法

用 Pillow 的 `paste` + `composite` 加 `linear_gradient` mask 已经足够，不需要 OpenCV 的特征匹配。GoodNotes 导出的 PDF 页面几何是精确的，不需要对齐。

### 5.3 切片高度需要可调

默认 2000px 是一个经验值。横向模式下通过 `--tile-width` 控制列宽，纵向模式下通过 `--tile-height` 控制行高。字小或图大时调小尺寸以保持局部分辨率；内容稀疏时调大以节省 tile 数量。

### 5.4 元数据比图片本身更重要

没有 `global_x` / `global_y` 和 `overlap_*`，下游模型很难把各 tile 识别结果拼回全局结构。metadata.json 是后续合并的关键。

---

## 6. 下一步可能方向

| 方向 | 说明 | 优先级 | 状态 |
|---|---|---|---|
| 横向切片 + 源文件附带 | 默认横向输出 `left_to_right_*.jpg`，附带原 PDF 与可搜索文本 | 高 | 2026-07-14 已完成 |
| tile 去重/合并脚本 | 把多个 tile 的识别结果按 metadata 合并成全局 graph | 高 | 待做 |
| macOS 启动器 | Spotlight/Dock 可启动的 `.app`，降低使用摩擦 | 高 | 2026-07-14 已完成 |
| prompt 工程层 | 自动生成 CRoC 框架 prompt.md + upload/ 目录 | 高 | 2026-07-14 已完成 |
| 支持 `.goodnotes` 原生输入 | 基于 goodparse 提取矢量笔画，避免 PDF 分页/失真 | 中 | 待做 |
| 输出 Mermaid/Markdown | 把识别结果转成可直接渲染的思维导图 | 中 | 待做 |
| 自动 tile 大小优化 | 根据画布尺寸和内容密度动态计算 tile 尺寸 | 低 | 待做 |

---

## 7. 相关链接与参考

- PyMuPDF docs: https://pymupdf.readthedocs.io/
- Pillow docs: https://pillow.readthedocs.io/
- goodparse（.goodnotes 解析参考）: https://github.com/franzthiemann/goodparse
- 手动识别报告：`/Users/mac/Downloads/gn2graph-output.md`
