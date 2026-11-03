# 02 — Pitch Resolution (`core/resolver.py`)

`FretboardResolver.resolve_neck_state(neck, fret, engaged_levers, target_root_name=None, target_chord_type=None, target_scale_name=None) -> List[ActiveStringState]`

This is the single source of truth for "what does each string sound like". Every engine and every UI view goes through it, and `core/stances.py` builds functional roles and shape verification on top of it.

## Algorithm

```
1. Choose the harmonic formula:
     root given & != "None"  → root_pc = NOTE_TO_SEMITONE[root.capitalize()]
     scale given & known     → formula = SCALE_FORMULAS[scale]     (scale beats chord)
     elif chord known        → formula = CHORD_FORMULAS[chord]
2. active_half_stops = {(controller_id, string): delta for active HalfStopRules}
3. active_splits     = {(string, frozenset(controllers)): delta for active SplitRules with ≥2 controllers}
4. For each engaged id:
     is_half = id.endswith("_HALF");  base = id without "_HALF"
     skip if base is not a pedal or knee lever on this neck
     for each (string, full_delta) in controller.changes:
         eff = active_half_stops.get((base,string)) if is_half, else default ±1   (half)
             = full_delta                                                         (full)
         pulls[string].append((base, eff, is_half))
5. For each string in open_tuning order:
     n = len(pulls)
     n == 0 → delta 0
     n == 1 → delta = that pull's eff               (NEVER a split, even if half)
     n >= 2 → tokens = {id + "_HALF" if half else id};  bases = {id}
              delta = active_splits[(string, tokens)]   if present   (engagement-aware rule)
                    else active_splits[(string, bases)] if present   (base-ID rule)
                    else sum(eff)
     active_midi = open_midi + fret + delta
     interval_label = formula.get((pc - root_pc) % 12)   if a formula is set
6. Return ActiveStringState(string_number, open_midi, active_midi, active_note_name (sharps),
                            pitch_class, interval_label, is_chord_tone, is_split_applied, is_half_stop)
```

## Behaviors to preserve

- **Unknown controller IDs are ignored silently.** This is what makes stale IDs (`VL` after the rename, `P1HS`) fail without any error.
- `is_half_stop` is true when *any* pull on the string is a half-stop, including when a split overrides it.
- Note names are always rendered with **sharps** (`midi_to_note_name(prefer_flat=False)`).
- Scale analysis wins over chord analysis when both are passed. The canvas clears one when setting the other.
- `target_root_name="None"` (the string) means no analysis.

## Known semantic gaps (design decisions to make, not bugs to patch blindly)

1. **Half-stop + split interaction (decided).** Split rules may list half tokens (`"P1_HALF"`). An exact token match wins; otherwise the base-ID rule applies (backward compatible). This also covers the 12U-3HS preset. Still open: whether a base-ID rule *should* apply to a half engagement when no half rule exists.
2. **Three-way conflicts.** A two-controller rule doesn't fire when a third controller also pulls the string, and the result falls back to the raw sum. Real changers usually resolve to "the most extreme raise wins" or similar. Consider a fallback policy (`max raise`, `max lower`, `sum`) per neck.
3. **Open-tuning order.** The resolver iterates `open_tuning`, and the canvas places rows by `string_number - 1`. Both assume contiguous 1..N.

## Ergonomics (`core/ergonomics.py`) — feasibility filter, not pitch

`ErgonomicsEngine.evaluate_stance(ids)` → `ErgonomicStance(is_possible, difficulty, penalty, description, clash_reasons)`

| Rule | Result |
|---|---|
| More than 2 pedals | impossible |
| 2 pedals not adjacent (by number) | impossible |
| More than 1 of {LKL, LKR, LKV} | impossible |
| More than 1 of {RKL, RKR, RKV} | impossible |
| Contact points (pedal = 1, split pedal = 1.5, each knee = 1) ≤ 1 | NATURAL, penalty 0 |
| ≤ 2.5 | STANDARD, penalty 3.0 for two pedals, else 1.5 |
| > 2.5 | AWKWARD, penalty 12 |

Callers strip `_HALF` before evaluating. Pedal adjacency uses ID numbers, so it is correct only when IDs are physical positions (rule A-2). `VL`, `RKR2` and `CK*` are not in the knee sets and are never checked for clashes.
