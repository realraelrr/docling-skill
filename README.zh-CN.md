# docling-skill

`docling-skill` 是一个构建在 [Docling](https://github.com/docling-project/docling) 之上的、面向 Agent 的 PDF ingestion 层。

[English README](README.md)

它会把 PDF 转成三类适合 LLM Agent 直接消费的产物：

- `foo.md`：面向 Agent 的 Markdown 正文
- `foo.images.json`：带稳定占位符和 base64 的图片 sidecar
- `foo.manifest.json`：质量、补救路径和路由决策元数据

核心原则很简单：Agent 不应该直接盲信提取出来的 Markdown，而应该先读 manifest，再决定结果是否可用。

## 为什么要有这个项目

Docling 的强项是文档解析。`docling-skill` 补的是面向 Agent 的消费契约：

- manifest-first 消费方式
- 稳定图片占位符，例如 `[[image:picture-p3-0]]`
- 面向 Agent 的质量门禁
- OCR 补救
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

先转换一个 PDF：

```bash
docling-skill "/path/to/file.pdf" "/tmp/docling-sidecar"
```

在消费 Markdown 之前，先检查 manifest：

```bash
python3 -c 'import json, pathlib; p = pathlib.Path("/tmp/docling-sidecar/file.manifest.json"); m = json.loads(p.read_text(encoding="utf-8")); print({"status": m["quality"]["status"], "reasons": m["quality"]["reasons"], "selected_attempt": m["selected_attempt"]})'
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

- `/tmp/docling-sidecar/file.md`
- `/tmp/docling-sidecar/file.images.json`

## CLI

```bash
docling-skill "<input_pdf>" "<output_dir>"
```

等价的模块入口：

```bash
python -m docling_skill.cli "<input_pdf>" "<output_dir>"
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

from docling_skill import convert_pdf_to_sidecar_outputs

outputs = convert_pdf_to_sidecar_outputs(
    pdf_path=Path("/path/to/file.pdf"),
    output_dir=Path("/tmp/docling-sidecar"),
)

manifest = outputs["manifest"]
if manifest["quality"]["status"] != "good":
    raise RuntimeError(manifest["quality"])

markdown_text = outputs["markdown_text"]
images = outputs["images"]
```

## 输出契约

对于 `foo.pdf`，CLI 会写出：

- `foo.md`
- `foo.images.json`
- `foo.manifest.json`

其中 `foo.manifest.json` 是下游 Agent 的控制平面。

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

## 图片 Sidecar

Markdown 中会出现形如 `[[image:picture-p2-1]]` 的占位符。

你可以用这个占位符去 `foo.images.json` 中找到对应图片，再按当前运行时支持的多模态输入方式传给模型。

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
- OCR 补救路径必须显式、可检查
- 如果只是少数页面质量差，优先做 page-level remediation，而不是整篇重跑

## 与上游的边界

`docling-skill` 依赖官方 `docling`。

目前它和 `pdf-ingest` 工作 fork 之间已知只有一个差异点：

- fork 中有一处 `hf_model_download.py` 的 SOCKS 代理兼容补丁
- 这个补丁没有被直接复制进 `docling-skill`

详情见 [UPSTREAM_GAPS.md](UPSTREAM_GAPS.md)。
