# docling-skill

`docling-skill` 是一个构建在 [Docling](https://github.com/docling-project/docling) 之上的、本地优先、面向 Agent 的文档规范化与 ingestion 层。

[English README](README.md)

它会把本地文档产物转成 workflow-ready 的标准产物：

- `source.md`：面向 Agent 的 Markdown 正文
- `source.images.json`：在支持提图时输出、带稳定占位符和 base64 的图片 sidecar
- `source.manifest.json`：质量、补救路径和路由决策元数据
- `source.meta.json`：供下游 agent 和 workflow 主控读取的轻量 ingestion 元数据

核心原则很简单：Agent 不应该直接盲信提取出来的 Markdown，而应该先读 manifest，再决定结果是否可用。

## Workflow 边界

`docling-skill` 在整个知识库 workflow 里只负责 ingestion：

- 直接输出 `source.*` 契约
- 当前接受本地 `pdf`、`docx`、`html`、`txt`、`md` 输入
- 保留 manifest-first 质量控制面
- 不负责 chunking，chunking 属于 ingestion 之后的通用 normalize 阶段
- 不负责标签、关键词、资料分类、一句话摘要等知识库语义字段
- 不负责远程 URL 抓取；远程获取属于上游 fetcher / browser 层

## 为什么要有这个项目

Docling 的强项是文档解析。`docling-skill` 补的是面向 Agent 的消费契约：

- manifest-first 消费方式
- 稳定图片占位符，例如 `[[image:picture-p3-0]]`
- 面向 Agent 的质量门禁
- 面向 PDF 工作流的 OCR 补救
- 针对局部弱页的 page-level remediation
- 明确的结果状态：`good`、`salvaged`、`failed_for_agent`

这个仓库刻意保持为官方 `docling` 之上的薄层，而不是长期维护整个上游 fork。

## 快速开始

```bash
pip install "git+https://github.com/realraelrr/docling-skill.git@v0.1.0"
docling-skill "/path/to/file.pdf" "/tmp/docling-sidecar"
```

如果你的运行环境使用 SOCKS 代理，建议额外安装：

```bash
pip install "git+https://github.com/realraelrr/docling-skill.git@v0.1.0"
pip install socksio
```

如果是本地开发：

```bash
git clone https://github.com/realraelrr/docling-skill.git
cd docling-skill
pip install -e .
```

## 首页示例

先转换一个本地文档：

```bash
docling-skill "/path/to/file.docx" "/tmp/docling-sidecar"
```

在消费 Markdown 之前，先检查 manifest：

```bash
python3 -c 'import json, pathlib; p = pathlib.Path("/tmp/docling-sidecar/source.manifest.json"); m = json.loads(p.read_text(encoding="utf-8")); print({"status": m["quality"]["status"], "reasons": m["quality"]["reasons"], "selected_attempt": m["selected_attempt"]})'
```

典型输出：

```json
{
  "status": "good",
  "reasons": [],
  "selected_attempt": "primary"
}
```

只有在这一步之后，Agent 才应该继续消费：

- `/tmp/docling-sidecar/source.md`
- `/tmp/docling-sidecar/source.images.json`
- `/tmp/docling-sidecar/source.meta.json`

## CLI

```bash
docling-skill "<input_path>" "<output_dir>"
```

等价的模块入口：

```bash
python -m docling_skill.cli "<input_path>" "<output_dir>"
```

可选参数：

```bash
--ocr-engine auto|tesseract|ocrmac|rapidocr
--ocr-lang <lang>
--force-full-page-ocr
--no-ocr-remediation
```

## Python API

```python
from pathlib import Path

from docling_skill import convert_document_to_ingestion_outputs

outputs = convert_document_to_ingestion_outputs(
    input_path=Path("/path/to/file.html"),
    output_dir=Path("/tmp/docling-sidecar"),
)

manifest = outputs["manifest"]
if manifest["quality"]["status"] != "good":
    raise RuntimeError(manifest["quality"])

markdown_text = outputs["markdown_text"]
images = outputs["images"]
meta = outputs["meta"]
```

## 输出契约

CLI 会写出：

- `source.md`
- `source.images.json`
- `source.manifest.json`
- `source.meta.json`

其中 `source.manifest.json` 是下游 Agent 的控制平面，`source.meta.json` 是下游 workflow 的桥接元数据。

当前阶段的 workflow 契约只包含这些输出文件；这一阶段没有单独的 `source.docling.json` 产物。

重点字段：

- `manifest["quality"]["status"]`
- `manifest["quality"]["agent_ready"]`
- `manifest["quality"]["reasons"]`
- `manifest["quality"]["content_trust"]`
- `manifest["selected_attempt"]`
- `manifest["ocr_remediation_applied"]`

状态含义：

- `good`：默认可安全交给下游 Agent
- `salvaged`：可用，但来自补救路径
- `failed_for_agent`：不要当成干净的 ingestion 结果使用

`source.meta.json` 的字段范围固定为 ingestion 阶段可知信息：

- `job_id`
- `input_type`
- `source_title`
- `source_url`
- `source_attachment`
- `author`
- `published_at`
- `extractor`
- `pipeline_family`
- `quality_status`
- `quality_reasons`
- `char_count`

它不承载标签、关键词、资料分类、一句话摘要等知识库语义字段。

## 图片 Sidecar

Markdown 中会出现形如 `[[image:picture-p2-1]]` 的占位符。

图片提取并不是所有已支持格式都统一具备。只有在 `source.images.json` 中确实存在对应条目时，才使用这个占位符去解析图片，再按当前运行时支持的多模态输入方式传给模型。

当前图片处理边界：

- 本地 PDF 中的嵌入图片是支持的。
- 其他本地格式在 Docling 暴露图片时也可能产出 sidecar，但不要默认认为所有格式行为一致。
- HTML / 网页图片抓取应由更大 workflow 里的 fetcher / browser 层负责，而不是这个 ingestion 步骤。

每条图片记录包含：

- `id`
- `placeholder`
- `page_no`
- `bbox`
- `mime_type`
- `base64`

## 设计原则

- Markdown 保持 text-first，不内嵌图片 base64
- Agent 的信任决策应来自 manifest，而不是在下游再堆一层临时 heuristics
- OCR 补救路径在启用时必须显式、可检查
- 如果只是少数页面质量差，优先做 page-level remediation，而不是整篇重跑

## 与上游的边界

`docling-skill` 依赖官方 `docling`。

当前本地 workflow 契约支持 `pdf`、`docx`、`html`、`txt`、`md`。

OCR 相关参数主要对 PDF 输入有意义。像 DOCX、HTML、TXT、Markdown 这样的 text-native 格式通常不需要 PDF 那套补救路径。

Docling 上游支持的格式更广，但这些能力在当前 workflow phase 里仍然属于范围外，除非这里明确把它们纳入本地 `source.*` 契约。

目前它和 `pdf-ingest` 工作 fork 之间已知只有一个差异点：

- fork 中有一处 `hf_model_download.py` 的 SOCKS 代理兼容补丁
- 这个补丁没有被直接复制进 `docling-skill`

详情见 [UPSTREAM_GAPS.md](UPSTREAM_GAPS.md)。
