# context.md — gn2graph 项目上下文

> 本文件沉淀本项目的核心决策、踩坑记录和可复用经验。
> 更新时间：2026-07-04

---

## 1. 问题背景

用户核心需求：**识别 GoodNotes 单页超大 whiteboard 导出的 PDF**。

不是多页 PDF 的"跨页"问题，而是单页 whiteboard 画布导出为 PDF 后尺寸极大（例如 10970×4373 像素），直接喂给 AI 时会被严重 downscale，导致：
- 手写细字看不清
- 远距离的连接线/箭头丢失
- 结构关系断裂

## 2. 关键决策

### 2.1 采用 tiling（切片）而非整图缩放

直接缩小整图会丢失细节。采用垂直切片 + 重叠，确保：
- 每个 tile 保持较高分辨率
- 跨 tile 的节点和连接至少在一个 tile 中完整可见
- 相邻 tile 之间有重叠带，方便后续合并识别结果

### 2.2 从"内置 VLM"退到"纯本地切片器"

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

---

## 3. 实现细节

### 3.1 渲染

- 使用 PyMuPDF (`fitz`)
- 默认 200 DPI，已足够辨认手写
- 渲染后按最大宽度统一，再做垂直拼接

### 3.2 拼接

- 多页 PDF 先垂直拼接成一张长图
- 相邻页面之间用 Pillow 的 `linear_gradient` mask 做羽化重叠
- 重叠比例由 `--overlap` 控制（默认 5%）

### 3.3 切片

- 将长图按 `--tile-height`（默认 2000px）切成若干 tile
- tile 之间同样保留 `--overlap` 比例的重叠
- 不足一个 tile 高度的尾部也单独保存

### 3.4 metadata.json

包含关键字段：
- `canvas_size`：原始画布尺寸
- `tile_count`：tile 数量
- `tiles[].global_y` / `global_y_end`：每块在原始画布中的全局垂直坐标
- `tiles[].overlap_top` / `overlap_bottom`：每块上下重叠像素

下游合并识别结果时，可以用 `global_y` 把各 tile 的相对 bbox 转成全局坐标。

---

## 4. 测试结果

测试材料：`goodnotes-whiteboard-test-materials/test-editable.pdf`

- 原始画布：10970×4373 px
- tile-height=2000，overlap=5%
- 输出：3 个 tile（2000px / 2000px / 573px）

**重要发现**：原图中一条从 `Loop Eng.` 向右下方大弧度延伸到 `学术 / 原理层面的理解` 的青色长弧线，在切片后完整保留在 tile_001 中。这说明 tiling 方案能有效保留远距离连接关系，避免整图 downscale 导致的细线丢失。

人工精读识别结果见：项目内 `gn2graph-output.md`（按 `prompt.md` 生成的 5 部分报告）和 `graph-manual.json`。

---

## 5. 踩坑与经验

### 5.1 不要混淆"单页超大 whiteboard"和"多页 PDF"

早期曾误以为用户要解决多页 PDF 的跨页连接问题。实际上用户要的是**单页超大画布**被 AI 切片后的识别问题。后续沟通中已纠正。

### 5.2 不需要复杂图像拼接算法

用 Pillow 的 `paste` + `composite` 加 `linear_gradient` mask 已经足够，不需要 OpenCV 的特征匹配。GoodNotes 导出的 PDF 页面几何是精确的，不需要对齐。

### 5.3 切片高度需要可调

默认 2000px 是一个经验值。对于字特别小或图特别宽的 whiteboard，可能需要更小的 tile-height 以保持局部分辨率；对于内容稀疏的，可以更大以节省 tile 数量。

### 5.4 元数据比图片本身更重要

没有 `global_y` 和 `overlap_*`，下游模型很难把各 tile 识别结果拼回全局结构。metadata.json 是后续合并的关键。

---

## 6. 下一步可能方向

| 方向 | 说明 | 优先级 |
|---|---|---|
| tile 去重/合并脚本 | 把多个 tile 的识别结果按 metadata 合并成全局 graph | 高 |
| 支持 `.goodnotes` 原生输入 | 基于 goodparse 提取矢量笔画，避免 PDF 分页/失真 | 中 |
| 输出 Mermaid/Markdown | 把识别结果转成可直接渲染的思维导图 | 中 |
| 自动 tile 大小优化 | 根据画布尺寸和内容密度动态计算 tile-height | 低 |

---

## 7. 相关链接与参考

- PyMuPDF docs: https://pymupdf.readthedocs.io/
- Pillow docs: https://pillow.readthedocs.io/
- goodparse（.goodnotes 解析参考）: https://github.com/franzthiemann/goodparse
- 手动识别报告：`/Users/mac/Downloads/gn2graph-output.md`
