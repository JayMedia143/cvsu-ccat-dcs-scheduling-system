---
name: Layout Designer Bug Fixes — Key Lessons
description: Bugs found and fixed during Layout Designer implementation; tricky gotchas to remember
type: feedback
---

## Bug 1: `UnboundLocalError: cannot access local variable 'Alignment'`

**Rule:** Inside `get_schedule_modal()`, never import openpyxl styles using the bare name `Alignment` — use aliased names.

**Why:** Python treats the entire function as having `Alignment` as a local variable the moment `from openpyxl.styles import Alignment` appears anywhere inside it — even below the line that uses it. The `Alignment` already used at line 3827 (`target_cell.alignment = Alignment(...)`) and the new import inside the same function create a scoping conflict.

**How to apply:** Always use underscore-aliased imports inside `get_schedule_modal()`:
```python
from openpyxl.styles import Font as _OFont, Alignment as _OAlignment, PatternFill as _OFill, Color as _OColor
```

---

## Bug 2: `cell_overrides` passed to renderer overwrites Phase 3b replacements

**Rule:** Always pass `cell_overrides=None` to `render_excel_to_html_exact()` in `get_schedule_modal()`.

**Why:** Phase 2 already bakes all cell text overrides (including `{{name}}`) into the ws in-place. Phase 3b then replaces `{{name}}` with the real entity name. If `cell_overrides` is passed to the renderer, it reads the RAW JSON value (`{{name}}`) instead of the Phase 3b-replaced value (`BSCoS 101-A`) — showing the placeholder literally.

**How to apply:** After Phase 2 + Phase 3b complete, call renderer with `cell_overrides=None`.

---

## Bug 3: openpyxl Color — 6-char RGB creates transparent black

**Rule:** When creating openpyxl `Color` from a hex string, always prefix with `FF` for opaque.

**Why:** `Color('000000')` (6 chars) gets padded by openpyxl to `'00000000'` — alpha=0 = transparent. Should be `'FF000000'` (alpha=FF = fully opaque).

**How to apply:**
```python
_fc_argb = ('FF' + _fc_raw.zfill(6)) if _fc_raw else None
color = _OColor(_fc_argb) if _fc_argb else _bf.color
```
Also for fill: `fgColor = 'FF' + bg.zfill(6)`

---

## Bug 4: LuckySheet `loadExcel` never calls success or error callback on silent failure

**Rule:** Always add a timeout (20 seconds) when loading Excel files into LuckySheet.

**Why:** LuckyExcel silently crashes (e.g., on corrupt/incompatible XLSX) without triggering any callback. Without a timeout, the "Restoring Layout..." spinner shows forever.

**How to apply:**
```javascript
let _loadDone = false;
const _loadTimeout = setTimeout(() => {
    if (!_loadDone) { _loadDone = true; renderGrid(null); loader(false); }
}, 20000);
// Inside success callback: clearTimeout(_loadTimeout); _loadDone = true;
```

---

## Bug 5: Phase 2 styles silently failing due to bare `except: pass`

**Rule:** Never use bare `except Exception: pass` in Phase 2 style application. Always at least `print()` the error.

**Why:** Silent exceptions hide real bugs (wrong Color format, bad font names, etc.) making it impossible to debug why styles aren't applying.

**How to apply:**
```python
except Exception as _e:
    print(f'[Phase2-font] {_coord} → {_e}')
```

---

## Bug 6: Phase 2 was inside `if entity_name:` block

**Rule:** Phase 2 (cell overrides + styles) must run OUTSIDE the `if entity_name:` check.

**Why:** Cell overrides and styles from LuckySheet should always be applied regardless of whether an entity was found. If entity_name is empty for any reason, all template customizations would be silently skipped.

**How to apply:** Move Phase 2 loop above `if entity_name:` block.

---

## Gotcha: LuckySheet `ht` alignment mapping

LuckySheet's `ht` field in celldata:
- `0` = center
- `1` = left
- `2` = right
- `3` = justify

Our `_ht_map` in `lucky_json_to_cell_styles` uses `{0: 'center', 1: 'left', 2: 'right', 3: 'justify'}` — this is correct.
Users expecting "center" should set `ht:0`, not `ht:2`.

---

## Gotcha: `_originalCells` and formula cells in LuckySheet

When a user deletes a formula cell (e.g., `=B10`) in LuckySheet, the cell becomes `v: null` in the JSON. Without tracking `_originalCells`, the draft save won't include this deletion, and on next load the formula restores. Fix: track which cells had original XLSX content and save explicit empty overrides when those cells are cleared.
