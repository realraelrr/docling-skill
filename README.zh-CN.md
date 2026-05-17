# docling-skill

`docling-skill` 是一个构建在 [Docling](https://github.com/docling-project/docling) 之上的本地优先、面向 Agent 的 ingestion 层。它把本地文档转换成稳定的 `source.*` sidecar 契约，方便 LLM agent 先检查质量，再安全消费内容。

[English README](README.md)

## 它做什么

当前支持的本地输入：`pdf`、`docx`、`xls`、`xlsx`、`csv`、`html`、`txt`、`md`。

每次成功转换都会写出：

| Artifact | 用途 |
| --- | --- |
| `source.manifest.json` | 质量、路由、补救路径和信任元数据 |
| `source.md` | Agent 默认读取的 Markdown |
| `source.docling.json` | 与 `source.md` 来自同一次转换结果的权威 Docling 结构化导出 |
| `source.images.json` | 始终写出的图片 sidecar 列表；无法提图或没有图片时为空数组 |
| `source.meta.json` | 供下游 workflow 使用的轻量 ingestion 元数据 |

下游消费规则：

1. 先读 `source.manifest.json`。
2. 如果 `quality.agent_ready` 为 true，默认读取 `source.md`。
3. 需要结构恢复、校正 Markdown 歧义或深入检查时，读取 `source.docling.json`。
4. 通过 `source.images.json` 解析 `[[image:picture-p2-1]]` 这类图片占位符。

`docling-skill` 不负责远程 URL 抓取、文档 chunking，也不输出标签、关键词、分类、摘要等下游知识库字段。

## 安装

```bash
pip install "git+https://github.com/realraelrr/docling-skill.git@v1.0.3"
docling-skill "/path/to/file.pdf" "/tmp/docling-sidecar"
```

如果运行环境使用 SOCKS 代理：

```bash
pip install "docling-skill[proxy] @ git+https://github.com/realraelrr/docling-skill.git@v1.0.3"
```

本地开发：

```bash
git clone https://github.com/realraelrr/docling-skill.git
cd docling-skill
pip install -e ".[proxy]"
```

## 使用

CLI：

```bash
docling-skill "<input_path>" "<output_dir>"
```

等价模块入口：

```bash
python -m docling_skill.cli "<input_path>" "<output_dir>"
```

偏 PDF/OCR 的可选参数：

```bash
--ocr-engine auto|tesseract|ocrmac|rapidocr
--ocr-lang <lang>
--force-full-page-ocr
--no-ocr-remediation
```

检查 manifest：

```bash
python3 -c 'import json, pathlib; p = pathlib.Path("/tmp/docling-sidecar/source.manifest.json"); m = json.loads(p.read_text(encoding="utf-8")); print({"status": m["quality"]["status"], "agent_ready": m["quality"]["agent_ready"], "selected_attempt": m["selected_attempt"]})'
```

Python API：

```python
from pathlib import Path

from docling_skill import convert_document_to_ingestion_outputs

outputs = convert_document_to_ingestion_outputs(
    input_path=Path("/path/to/file.html"),
    output_dir=Path("/tmp/docling-sidecar"),
)

manifest = outputs["manifest"]
if not manifest["quality"]["agent_ready"]:
    raise RuntimeError(manifest["quality"])

markdown_text = outputs["markdown_text"]
structured_document = outputs["docling_document"]
images = outputs["images"]
meta = outputs["meta"]
```

## Skill 引用格式

这个仓库用同一份源 skill 同时支持 Codex 和 Claude Code。

- Codex：`.codex/skills/docling-skill/SKILL.md`
- Claude Code：`.claude/skills/docling-skill/SKILL.md`
- Root source：`SKILL.md`

全局安装时，使用用户 home 目录下的同一套目标路径：

- Codex：`~/.codex/skills/docling-skill/SKILL.md`
- Claude Code：`~/.claude/skills/docling-skill/SKILL.md`

## Agent 配置

如果你是 Codex、Claude Code 或其他 LLM agent，需要从零安装配置这个项目：

1. 把这个仓库当作 source of truth。
2. 将仓库 clone 到用户的本地代码工作区。
3. 安装到现有的 `docling` conda 环境；如果配置了 SOCKS 代理，使用 `proxy` extra。
4. 让两个 agent skill entrypoint 都指向这个 repo 根目录下的 `SKILL.md`，优先使用 symlink，不要复制。
5. 使用当前运行时可用的 validator 验证 root skill 和两个安装路径下的 skill。
6. 运行测试套件。
7. 不要提交 `.state/` 或其他 agent working files。

预期验证：

```bash
# 如果 Codex skill validator 可用：
conda run -n docling python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
conda run -n docling python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .codex/skills/docling-skill
conda run -n docling python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .claude/skills/docling-skill

conda run -n docling python -m pytest
```

## 范围

`docling-skill` 是官方 `docling` 之上的薄 workflow 层，不是 Docling fork，也不是官方发行版。

Skill workflow 契约位于 [SKILL.md](SKILL.md)。Docling 支持的格式比本项目当前暴露的更多。新增格式时，必须先保证它能保留本地 `source.*` 契约、质量门禁和测试。

## 致谢

本项目构建在 [Docling](https://github.com/docling-project/docling) 之上，Docling 提供了解析器、文档模型和多格式支持。
