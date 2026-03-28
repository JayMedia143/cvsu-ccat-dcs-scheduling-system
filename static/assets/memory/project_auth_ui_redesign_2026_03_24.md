---
name: Auth UI Redesign (Login/Signup) — v2.25
description: Complete redesign of login.html and signup.html auth pages — final confirmed state including all text content
type: project
---

# Auth UI Redesign — Completed 2026-03-24 (text finalized same date)

Auth pages (login + signup) fully redesigned and confirmed working. User approved final result.

**Why:** Old auth pages were plain. User requested a dark showcase panel on the left with a 3D floating schedule card, plus a clean light form panel on the right.

**How to apply:** If touching auth CSS or templates, reference the final values below as ground truth.

---

## Final Text Content

| Element | login.html | signup.html |
|---------|-----------|-------------|
| `.auth-brand-title` | `CvSU-CCAT Scheduling System` | `CvSU-CCAT Scheduling System` |
| `.auth-brand-subtitle` | `Semi-automated class scheduling powered by Genetic Algorithm.` | `Create your account and start managing class schedules.` |
| `.auth-chrome-title` (card header) | `Schedule · 2026–2027` | `Schedule · 2026–2027` |
| `.auth-brand-footer` | `© 2025–2026 CvSU-CCAT Scheduling System` | `© 2025–2026 CvSU-CCAT Scheduling System` |

Notes:
- "Semi-automated" is intentional and accurate — GA automates optimization only; humans input data, trigger generation, and review output
- Footer year `2025–2026` = development period (NOT academic year)
- Card chrome `2026–2027` = academic year being scheduled (NOT dev year) — keep separate

---

## Layout Structure

Two-panel full-viewport layout (`display: flex` on `body.auth-page`):

- **`.auth-left`** — 55% width, dark green gradient background, 3-child `space-between` column flex
  - Child 1: `.auth-brand-group` — horizontal (row) layout: icon left + brand text right
  - Child 2: `.auth-card-zone` — centered card zone (full width, `justify-content: center`)
  - Child 3: `.auth-brand-footer` — copyright line, `position: relative` (in-flow, NOT absolute)
- **`.auth-right`** — 45% width, light panel with login/signup form

---

## Final CSS Values (style.css)

```css
.auth-left {
    width: 55%;
    background: linear-gradient(160deg, #0a0f0b 0%, #0f1a11 60%, #0a0f0b 100%);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    align-items: flex-start;
    padding: 3.5rem 2rem 3rem;
    overflow: hidden;
}

.auth-brand-group {
    display: flex;
    flex-direction: row;   /* horizontal */
    align-items: center;
    gap: 1.25rem;
}

.auth-icon-wrap {
    width: 64px;
    height: 64px;
    border-radius: 16px;
    font-size: 1.8rem;
}

.auth-brand-title {
    font-size: 1.7rem;
    font-weight: 900;
    line-height: 1.1;
}

.auth-brand-footer {
    position: relative;   /* in-flow flex child — NOT position: absolute */
}

.auth-card-zone {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
}

.auth-3d-card {
    width: 100%;
    max-width: 680px;    /* fixed cap — not 100%, not 560px */
    transform: perspective(900px) rotateX(8deg) rotateY(-12deg) rotateZ(-1deg);
    animation: floatCard 5s ease-in-out infinite;
}

@keyframes floatCard {
    0%, 100% { transform: perspective(900px) rotateX(8deg) rotateY(-12deg) rotateZ(-1deg) translateY(0px); }
    50%       { transform: perspective(900px) rotateX(5deg) rotateY(-10deg) rotateZ(-0.5deg) translateY(-12px); }
}

.auth-card-slot {
    flex: 1;
    height: 40px;   /* was 28px — increased for bigger card appearance */
    border-radius: 6px;
    font-size: 0.55rem;
}
```

---

## Card Structure (login.html / signup.html)

- 9 time columns (7–8, 8–9, 9–10, 10–11, 11–12, 1–2, 2–3, 3–4, 4–5)
- 6 day rows (MON, TUE, WED, THU, FRI, SAT)
- Slot colors: `slot-green`, `slot-teal`, `slot-lime`, `slot-blue`, `slot-empty`

---

## Key HTML Notes

- NO `<br>` inside `.auth-brand-title` — title is one line: "CvSU-CCAT Scheduling System"
- NO `<div class="auth-accent-line"></div>` inside `.auth-brand-text` — accent line only in `.auth-right .auth-form-box`
- `.auth-brand-footer` is the LAST child of `.auth-left`, not inside any other wrapper

---

## Common Pitfalls (from iteration history)

| Mistake | Effect | Fix |
|---------|--------|-----|
| `max-width: 100%` on `.auth-3d-card` | Card stretches wall-to-wall | Use fixed `max-width: 680px` |
| `position: absolute` on `.auth-brand-footer` | Footer leaves flex flow → only 2 space-between children → card pushed to bottom | Keep `position: relative` |
| `flex: 1` on `.auth-card-zone` | Zone consumes all remaining height → card floats at center of giant empty zone | Use `flex: none` |
| `align-items: flex-start` without `width: 100%` on `.auth-card-zone` | Card zone shrinks to content width | Keep `width: 100%` on `.auth-card-zone` |
| `<br>` in title | Title looks cramped/squeezed in horizontal layout | Remove `<br>` |
| `rotateY(+10deg)` | Tilts wrong direction for left panel | Use `rotateY(-12deg)` |
