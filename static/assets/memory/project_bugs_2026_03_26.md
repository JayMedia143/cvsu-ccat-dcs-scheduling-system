---
name: Bugs reported 2026-03-26 (unresolved)
description: Four bugs reported by user on 2026-03-26 that still need fixes
type: project
---

Bugs reported this session — partially or fully unresolved as of 2026-03-26.

**Why:** Session context ran out mid-implementation; some fixes listed in memory as "done" on 2026-03-25 did not actually get saved or had wrong approach.

**How to apply:** Treat all four as unresolved. Verify each in code before assuming done.

---

## Bug 1 — Images disappear on 2nd view (BytesIO exhaustion)

**Symptom:** Section/faculty/room/course timetable shows images on 1st view, images gone on 2nd+ view. Even after Flask restart: 1st view works, 2nd doesn't.

**Root cause:** `_get_cached_template()` caches the openpyxl worksheet. When `_extract_ws_images_html()` calls `img._data()`, it reads the internal BytesIO to EOF. Second call from cache: BytesIO is exhausted → empty bytes → no image.

**Correct fix (NOT yet verified in code):** In `_get_cached_template`, after loading ws, pre-extract all image bytes into `ws._cached_img_bytes = {i: bytes}`. In `_extract_ws_images_html`, use `ws._cached_img_bytes[i]` instead of `img._data()`. This reads BytesIO exactly once.

**Status:** Listed as fixed in memory (project_image_zorder_bytesio_2026_03_25.md) but user confirmed still broken 2026-03-26. Re-verify and re-apply.

---

## Bug 2 — Z-order "Below Text" renders above table

**Symptom:** When Z-Order = "Below Text", image still appears on top of grid/borders/text — should be behind the table.

**Root cause:** `position:absolute` always renders above `position:static` elements regardless of DOM order. The outer wrapper div has no isolated stacking context.

**Correct fix:**
1. Add `z-index:2` (above) / `z-index:0` (below) to image `_style` in `_extract_ws_images_html`
2. Add `isolation:isolate` to outer wrapper div in `render_excel_to_html`
3. Wrap `'\n'.join(lines)` table in `<div style="position:relative;z-index:1;">`

**Status:** Plan approved (lucky-knitting-puffin.md at one point), listed as fixed in memory 2026-03-25, but user confirmed still broken 2026-03-26. Re-apply.

---

## Bug 3 — Login flash: dashboard visible split-second before loader

**Symptom:** After successful login, dashboard content is briefly visible before the loader overlay appears. Affects all user roles (superadmin, admin, user).

**Root cause:** Page renders HTML first, then JS runs to show loader. By the time the loader shows, the dashboard has already painted.

**Correct fix:** Add `display:none` to `<body>` via inline `<style>` in base.html (or dashboard template), then JS removes it after setting up loader. OR: render loader as a static element visible by default (no JS needed to show it), hidden only after page is ready.

**Status:** Not implemented.

---

## Bug 4 — Generate schedule returns 400

**Symptom:** `POST /start-generation` → HTTP 400. Confirmed in Flask logs:
```
"POST /start-generation HTTP/1.1" 400
"POST /stop-generation HTTP/1.1" 400
```

**Root cause:** CSRF token mismatch. The X-CSRFToken header fix was applied in 2026-03-25 session but may not have saved correctly, or the generate_schedule.html fetch() call is still missing the header.

**Status:** Listed as fixed in memory (project_login_loader_csrf_blocked_slots_2026_03_25.md) but user confirmed broken 2026-03-26. Re-check generate_schedule.html fetch() calls for `'X-CSRFToken': csrfToken` header.
