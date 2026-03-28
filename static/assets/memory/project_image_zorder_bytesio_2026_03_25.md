---
name: Image Z-Order Fix + BytesIO Cache Bug Fix
description: Two image rendering bugs fixed: z-order (below text not working) and images disappearing after first view due to openpyxl BytesIO exhaustion
type: project
---

## Status: FIXED (2026-03-25)

**Why:** After adding per-image adjustment controls (x/y/scale/z-order in manage_layouts), two bugs were found in how images are rendered in timetable HTML output.

**How to apply:** All fixes are in `app.py` and `genetic_algorithm.py`. The z-order fix uses CSS stacking contexts; the BytesIO fix pre-caches image bytes at template load time.

---

## Bug 1 — "Below Text" z-order doesn't work (images always on top)

**Root cause:** `position:absolute` elements ALWAYS render on top of `position:static` elements in the same stacking context, regardless of DOM order. Placing `imgs_below` before the `<table>` in HTML had no effect.

Also: using `z-index:-1` made images invisible (sent behind the entire document).

**Fix — 2 changes in `render_excel_to_html` + `_extract_ws_images_html` (app.py):**

1. `_extract_ws_images_html` `_style` list: add `'z-index:2' if _z_above else 'z-index:0'`
2. `render_excel_to_html` wrapper div: add `isolation:isolate` + wrap table in `<div style="position:relative;z-index:1;">`

**CSS stacking layers:**
- `z-index:0` = below-images (behind table)
- `z-index:1` = table wrapper (grid + borders + text)
- `z-index:2` = above-images (on top of table)

`isolation:isolate` creates a self-contained stacking context so z-index values don't leak outside.

---

## Bug 2 — Images disappear after first view (second render always blank)

**Root cause:** `_get_cached_template` caches the openpyxl `Worksheet` object. The `ws._images` list contains `Image` objects whose data is stored in a `BytesIO` stream. `_extract_ws_images_html` calls `img._data()` which internally calls `PIL.open(ref) → fp.read() → fp.close()`. After `close()`, the BytesIO is permanently closed. The second render from cache gets empty bytes → images silently skipped.

**Why seek(0) didn't work:** `fp.close()` closes the BytesIO entirely. `seek(0)` on a closed BytesIO raises `ValueError`, caught silently.

**Fix — 2 changes in app.py:**

1. `_get_cached_template` (~line 7155): pre-extract all image bytes before caching:
   ```python
   ws._img_bytes_cache = []
   for _img in getattr(ws, '_images', []):
       try:
           ws._img_bytes_cache.append(_img._data())
       except Exception:
           ws._img_bytes_cache.append(b'')
   ```

2. `_extract_ws_images_html` (~line 5926): use cached bytes instead of `img._data()`:
   ```python
   _img_bytes_cache = getattr(ws, '_img_bytes_cache', None)
   for i, img in enumerate(getattr(ws, '_images', [])):
       if _img_bytes_cache is not None and i < len(_img_bytes_cache):
           raw = _img_bytes_cache[i]
       else:
           raw = img._data()
   ```

**Key insight:** Bytes are extracted exactly once (at cache-load time), stored as plain `list[bytes]`, no streams involved. Every subsequent render reads from this list.
