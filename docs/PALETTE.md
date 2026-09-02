# Palette

The default palette is a validated set. The slot **ordering** is the
colorblind-safety mechanism, not a cosmetic choice: candidate orderings were
enumerated and only those clearing every adjacent-pair gate in both modes kept.

## Categorical slots

Assign in this order. Never cycle past slot 8.

| Slot | Hue | Light | Dark |
|---|---|---|---|
| 1 | blue | `#2a78d6` | `#3987e5` |
| 2 | orange | `#eb6834` | `#d95926` |
| 3 | aqua | `#1baf7a` | `#199e70` |
| 4 | yellow | `#eda100` | `#c98500` |
| 5 | magenta | `#e87ba4` | `#d55181` |
| 6 | green | `#008300` | `#008300` |
| 7 | violet | `#4a3aa7` | `#9085e9` |
| 8 | red | `#e34948` | `#e66767` |

## Validation record

Measured in OKLab ΔE × 100. Adjacent-pair target ≥ 8 for simulated CVD, with a
hard normal-vision floor of 15.

| Check | Worst CVD ΔE | Worst normal ΔE | Result |
|---|---|---|---|
| Light, adjacent pairs (8 slots) | 9.1 | 19.6 | PASS |
| Dark, adjacent pairs (8 slots) | 8.4 | 19.3 | PASS |
| Light, all pairs (first 3 slots) | 9.2 | 24.0 | PASS |
| Dark, all pairs (first 3 slots) | 9.4 | 20.9 | PASS |

Surfaces: light `#fcfcfb`, dark `#1a1a19`.

**The all-pairs cap.** Forms that place every series against every other one -
`scatter` above all - cannot seat more than three hues: with all 28 pairs in
play, no ordering of the eight clears the floors. `theme.ALL_PAIRS_CAP` enforces
this, and `normalize` folds the tail into "Other" rather than seating a fourth.

**The relief rule.** Three light-mode hues sit below 3:1 contrast against the
light surface (`#1baf7a` 2.74, `#eda100` 2.11, `#e87ba4` 2.62). A contrast
warning is not dismissable: it obligates visible labels or a table view. This is
why **every render writes `NAME.md`** and why `--no-markdown` should be used
only when the values are being carried somewhere else.

## The other ramps

- **Sequential**: one hue (blue), light to dark, 13 steps. For continuous
  magnitude - heatmaps. Never a rainbow.
- **Ordinal**: the sequential ramp trimmed at both ends so the step nearest the
  surface still clears 2:1. For discrete ordered marks.
- **Diverging**: blue ↔ red - warm and cool poles that read as opposite - with a
  neutral gray midpoint (`#f0efec` light, `#383835` dark). Blue ↔ aqua was
  rejected: both are cool, so the midpoint does not read as "nothing".
- **Status** (reserved, never themed, never reused for a series):
  good `#0ca30c`, warning `#fab219`, serious `#ec835a`, critical `#d03b3b`.
  On the light surface, warning and serious are sub-3:1 by design; the icon plus
  label pairing is the mitigation, so a status color never carries meaning alone.

## Retheming

Everything lives in `src/agent_charts/theme.py`. Replace the values there, then:

1. Run the data-viz skill's `scripts/validate_palette.js` against **your own**
   surfaces, in both modes:
   ```
   node validate_palette.js "<hex,hex,...>" --mode light --surface <your-light>
   node validate_palette.js "<hex,hex,...>" --mode dark  --surface <your-dark>
   ```
2. Run it again with `--pairs all` on the leading slots to find your own
   all-pairs cap, and update `ALL_PAIRS_CAP`.
3. Update the table above with what the validator reported.
4. Update `tests/test_theme.py`, which pins the current set deliberately so a
   silent recolor cannot land.

Do not eyeball whether a palette is colorblind-safe. Run the script.

## Checking the current palette

```bash
chart-gen palette          # the slots and the validation record
chart-gen palette --json   # the same, machine-readable
```
