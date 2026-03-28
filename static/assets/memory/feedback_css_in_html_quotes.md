---
name: CSS font-family quotes in HTML style attributes
description: Never use double quotes inside CSS values when the HTML style attribute itself uses double quotes — it silently breaks all CSS after the quoted value
type: feedback
---

When embedding CSS inside an HTML `style="..."` attribute, never use double quotes inside the CSS value strings — they prematurely close the HTML attribute and silently drop all CSS properties that follow.

**Why:** `style="font-family:"Arial Narrow",sans-serif;font-weight:bold"` — the browser sees the `"` before `Arial` as closing the attribute. Everything after `font-family:` (bold, color, borders, alignment) is dropped with no error.

**How to apply:** Always use CSS single quotes for font-family values in Python f-strings:
```python
# WRONG:
f'font-family:"{fname}",sans-serif'

# CORRECT:
f"font-family:'{fname}',sans-serif"
```
This applies to any CSS string value that may contain spaces (font names, content values, etc.) when injected into a double-quoted HTML attribute.
