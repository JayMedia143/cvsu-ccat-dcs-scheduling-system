---
name: Section Preview Pixel-Perfect Renderer — 2026-03-17
description: All fixes made to make the Section timetable HTML preview pixel-accurate vs Excel file
type: project
---

Session date: 2026-03-17

## Problem: TIME/DAYS column rendered wider than 77px
- **Root cause**: `table-layout:fixed; width:100%` proportionally scales all columns when `_orig_total_w_px (442px) < paper_content_px (698px)`. So `width:77px` on `<col>` became `77/442 × 698 = 121px`.
- **Fix**: Section layout only — TIME/DAYS `<col>` gets `width:{w}px` (fixed), day columns get `width:auto`. Browser distributes `(698px - 77px)` equally among 6 day cols.

**Why:** `table-layout:fixed` + `width:100%` scales ALL columns proportionally unless some are marked auto.
**How to apply:** Only section layout uses this treatment. Faculty/Room/Course still use `%` widths.

## Problem: Content not reaching right edge of paper (gap on right)
- **Root cause**: JS was applying `transform: scale(scaleH)` uniformly (X+Y), compressing table width.
- **Fix**: Changed to `transform: scale(1, scaleH)` — height-only compression preserves full table width.
- Also changed JS from `table.scrollWidth` to `table.offsetWidth` (scrollWidth was inflated by `white-space:pre` cell overflow).

## Problem: Logo image shifted right by ~1.58× in section preview
- **Root cause**: `left_pct = left_ref / _orig_total_w_px * 100` but table renders at `_paper_content_px`. Ratio `698/442 = 1.58`.
- **Fix**: For section layout, pass `_paper_content_px = (pw - ml - mr) × 96` as `total_w_px` to `_extract_ws_images_html`.

## Row heights: removed top/bottom cell padding
- Changed `padding:2px 4px 2px {_pad_left}px` → `padding:0 4px 0 {_pad_left}px`
- Removes 2px top + 2px bottom so row heights better match Excel.

## Pre-start column offset bug (anchor in col A when table starts col B)
- **Root cause**: `_orig_col_offsets` only had keys `0..n` (relative to col_start). Anchor at col A (`fr.col=0`) with `col_start=2` → key `-1` → fallback to 0. Missing col A width correction.
- **Fix**: Extended `_orig_col_offsets` with negative keys for pre-start columns:
  ```python
  if col_start > 1:
      _pre_acc = 0
      for _c in range(col_start - 1, 0, -1):
          _cd = ws.column_dimensions.get(get_column_letter(_c))
          _cw = 0 if (_cd and _cd.hidden) else max(4, round((_cd.width if _cd and _cd.width else 8.43) * MDW))
          _pre_acc += _cw
          _orig_col_offsets[_c - col_start] = -_pre_acc  # negative key
  ```

## Logo still slightly too far right — 20px offset fix
- **Debug data**: `fr.col=2 fr.colOff=419100 left_ref=132.0px col_start=2 total_w_px=697.9 left_pct=18.91%`
- Logo anchor is in col C (0-based 2), 44px into it. col B Excel width = 88px (MDW-based), but HTML renders col B as 77px fixed. Difference + minor drift = ~20px.
- **Fix**: Added `left_offset_px=0` param to `_extract_ws_images_html`. Section layout passes `left_offset_px=-20`:
  ```python
  left_pct = (left_ref + left_offset_px) / total_w_px * 100
  ```
- Callers: `preview_layout` and `section_timetable_html/pdf` pass `left_offset_px=-20`.

## Function signatures updated
- `_extract_ws_images_html(ws, col_offsets, row_offsets, col_start, row_start, total_w_px=1, left_offset_px=0)`
- `render_excel_to_html(ws, variable_map, cell_overrides, extra_merge_map, extra_skip_cells, bounds, layout_type, margins)`
