---
name: View Timetable Ctrl+Scroll Zoom
description: Ctrl+Scroll zoom fix for view_timetable.html scroll mode — pointer-events:none on iframes when Ctrl held so wheel events reach parent window
type: project
---

# View Timetable Ctrl+Scroll Zoom — Completed 2026-03-20

**File:** `templates/view_timetable.html`

---

## Problem

Scroll mode shows multiple schedule iframes in a flex column (`#scrollPagesInner`).
There was already a `wheel` listener on `window` to zoom `#scrollPagesInner` with Ctrl+Scroll.
But when the mouse hovered over any iframe, wheel events were captured by the iframe's document —
the parent window never received them, so zoom never fired.

---

## Fix

Track Ctrl key state. While Ctrl is held, set `pointer-events: none` on all scroll iframes.
This makes iframes transparent to mouse events → wheel events pass through to parent window.
On Ctrl release, restore `pointer-events: ''` so iframes are interactive again.

```javascript
var _ctrlHeld = false;

function _setIframePointerEvents(val) {
    if (viewMode !== 'scroll') return;
    document.querySelectorAll('#scrollPagesInner iframe').forEach(function (fr) {
        fr.style.pointerEvents = val;
    });
}

document.addEventListener('keydown', function (e) {
    if ((e.key === 'Control' || e.key === 'Meta') && !_ctrlHeld) {
        _ctrlHeld = true;
        _setIframePointerEvents('none');
    }
});

document.addEventListener('keyup', function (e) {
    if (e.key === 'Control' || e.key === 'Meta') {
        _ctrlHeld = false;
        _setIframePointerEvents('');
    }
});

// Reset if window loses focus (e.g. Alt+Tab while holding Ctrl)
window.addEventListener('blur', function () {
    _ctrlHeld = false;
    _setIframePointerEvents('');
});

window.addEventListener('wheel', function (e) {
    if (!e.ctrlKey || viewMode !== 'scroll') return;
    e.preventDefault();
    scrollZoom += e.deltaY > 0 ? -0.08 : 0.08;
    scrollZoom = Math.max(0.2, Math.min(1.5, scrollZoom));
    document.getElementById('scrollPagesInner').style.zoom = scrollZoom;
}, { passive: false });
```

**Zoom limits:** 20% minimum, 150% maximum.
**Applied via:** `style.zoom` on `#scrollPagesInner` (scales all child iframes together).
**blur handler:** Prevents `pointer-events: none` getting stuck if user Alt+Tabs while holding Ctrl.

---

## Location in file
The entire block replaced the original single `wheel` listener at ~lines 274–281.
