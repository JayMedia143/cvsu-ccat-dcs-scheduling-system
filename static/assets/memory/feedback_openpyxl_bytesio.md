---
name: openpyxl Image BytesIO Exhaustion
description: Never call img._data() more than once on a cached openpyxl Image — PIL closes the underlying BytesIO permanently
type: feedback
---

When openpyxl images are loaded from a workbook, `img._data()` reads bytes via PIL. PIL calls `fp.close()` on the internal BytesIO after reading. The BytesIO is then permanently closed — `seek(0)` raises `ValueError: I/O operation on closed file`.

**Why:** PIL's `_data()` implementation: `img.fp.seek(0); data = fp.read(); fp.close()`. After `close()`, the stream is dead.

**How to apply:** If caching a `Worksheet` object across requests (e.g., via `_get_cached_template`), pre-extract all image bytes at cache-load time and store as `ws._img_bytes_cache = list[bytes]`. Then read from that list instead of calling `img._data()` again. This is implemented in `_get_cached_template` and `_extract_ws_images_html` in app.py.

Never try to `seek(0)` on `img.ref` as a workaround — it targets the wrong object and fails silently.
