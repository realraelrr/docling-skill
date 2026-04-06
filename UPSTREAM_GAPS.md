# Upstream Gaps

## SOCKS Proxy Download Compatibility

The current `pdf-ingest` fork contains a patch in `docling/models/utils/hf_model_download.py` that temporarily removes SOCKS-style proxy environment variables when `socksio` is unavailable.

`docling-skill` does not monkey-patch official `docling` to reproduce that behavior.

Implications:

- if your environment does not use SOCKS proxies, no action is needed
- if your environment uses SOCKS proxies, install `socksio`
- alternatively, upstream the patch or add an explicit compatibility layer later

Recommended mitigation for now:

```bash
pip install 'docling-skill[proxy]'
```
