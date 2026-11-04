"""Progression Studio model (E-32): one list of chord steps, each with a duration in beats, an
optional stance (fret, controllers, grip) and a play style. Replaces the separate voice leader
(chords -> voicings) and sequencer (stances -> playback) data. Qt-free.

- Chords are CHORD_FORMULAS types; stances come from VoiceLeadingEngine or the fretboard.
- A pinned stance (captured, from a preset, or set by hand) is kept by `fill_stances`; the
  others are re-solved around it. Changing a step's chord clears its stance, so playback can
  never use a voicing of a previous chord, progression or neck.
"""

import random
import re
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from core.models import Neck
from core.permutation_engine import PermutationEngine
from core.progression_presets import ProgressionPreset, resolve_preset_steps
from core.resolver import FretboardResolver
from core.scale_chords import chord_symbol
from core.stances import grip_pitch_classes
from core.tab_generator import TabStep
from core.theory import CHORD_FORMULAS, CHORD_SYMBOL_SUFFIX, NOTE_TO_SEMITONE, respell, spell_pc
from core.voice_leader import (
    ChordProgression,
    ChordSlot,
    ProgressionMeasure,
    UnknownChordTypeError,
    VoiceLeadingConstraints,
    VoiceLeadingEngine,
    normalize_chord_type,
)

STYLE_BLOCK, STYLE_ROLL, STYLE_ARPEGGIO = "block", "roll", "arpeggio"
STYLES = (STYLE_BLOCK, STYLE_ROLL, STYLE_ARPEGGIO)
TIME_SIGNATURES: Dict[str, int] = {"2/4": 2, "3/4": 3, "4/4": 4, "6/8": 6}


def beats_per_bar(time_signature: str) -> int:
    return TIME_SIGNATURES.get(time_signature, 4)


@dataclass
class StudioStep:
    root: Optional[str] = None
    chord_type: Optional[str] = None
    beats: int = 4
    fret: Optional[int] = None
    controllers: List[str] = field(default_factory=list)
    grip: List[int] = field(default_factory=list)
    pinned: bool = False
    style: str = STYLE_BLOCK
    perm_id: int = 2           # Franklin permutation for STYLE_ARPEGGIO
    label: str = ""            # shown when the step has no chord (e.g. an unnamed captured grip)

    @property
    def has_chord(self) -> bool:
        return bool(self.root and self.chord_type)

    @property
    def has_stance(self) -> bool:
        return self.fret is not None and bool(self.grip)

    @property
    def is_rest(self) -> bool:
        return not self.has_chord and not self.has_stance

    @property
    def symbol(self) -> str:
        if self.has_chord:
            return chord_symbol(respell(self.root), self.chord_type)
        if self.label:
            return self.label
        return "Grip" if self.has_stance else "Rest"

    def set_chord(self, root: Optional[str], chord_type: Optional[str]) -> None:
        """Changes the chord; a different chord clears the stance and the pin (D-45)."""
        if root and chord_type and chord_type not in CHORD_FORMULAS:
            raise UnknownChordTypeError(chord_type)
        new = (root, chord_type) if root and chord_type else (None, None)
        if new == (None, None):
            same = not self.has_chord
        else:
            same = (self.has_chord and NOTE_TO_SEMITONE.get(root) == NOTE_TO_SEMITONE.get(self.root)
                    and chord_type == self.chord_type)
        self.root, self.chord_type = new
        if not same:
            self.clear_stance()

    def set_stance(self, fret: int, controllers, grip, pinned: bool = False) -> None:
        self.fret = int(fret)
        self.controllers = sorted(controllers)
        self.grip = sorted(int(s) for s in grip)
        self.pinned = pinned

    def clear_stance(self) -> None:
        self.fret = None
        self.controllers = []
        self.grip = []
        self.pinned = False

    def to_dict(self) -> dict:
        return {
            "root": self.root, "type": self.chord_type, "beats": self.beats, "fret": self.fret,
            "controllers": list(self.controllers), "grip": list(self.grip), "pinned": self.pinned,
            "style": self.style, "perm": self.perm_id, "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StudioStep":
        ctype = d.get("type")
        if ctype:
            ctype = normalize_chord_type(ctype)
        return cls(
            root=d.get("root") or None, chord_type=ctype or None, beats=max(1, int(d.get("beats", 4))),
            fret=d.get("fret"), controllers=list(d.get("controllers", [])), grip=list(d.get("grip", [])),
            pinned=bool(d.get("pinned", False)), style=d.get("style", STYLE_BLOCK) if d.get("style") in STYLES else STYLE_BLOCK,
            perm_id=int(d.get("perm", 2)), label=d.get("label", ""),
        )


@dataclass
class StudioProgression:
    name: str = "Untitled progression"
    key: str = "G"
    time_signature: str = "4/4"
    tempo: int = 100
    steps: List[StudioStep] = field(default_factory=list)
    neck_name: str = ""  # the neck the stances were made for

    @property
    def beats_per_bar(self) -> int:
        return beats_per_bar(self.time_signature)

    def step_starts(self) -> List[int]:
        out, t = [], 0
        for s in self.steps:
            out.append(t)
            t += s.beats
        return out

    @property
    def total_beats(self) -> int:
        return sum(s.beats for s in self.steps)

    def bar_position(self, idx: int) -> Tuple[int, int]:
        """(bar, beat), both 1-based, where step idx starts."""
        start = self.step_starts()[idx]
        bpb = self.beats_per_bar
        return start // bpb + 1, start % bpb + 1

    # ---- .cp / .json (the voice leader's ChordProgression format, plus a "studio" block) ----

    def to_dict(self) -> dict:
        bpb = self.beats_per_bar
        starts = self.step_starts()
        total = self.total_beats
        measures = []
        for bar, bar_start in enumerate(range(0, max(total, 1), bpb)):
            slots = []
            for s, st in zip(self.steps, starts):
                begins_here = bar_start <= st < bar_start + bpb
                held_into_bar = st < bar_start < st + s.beats
                if begins_here or held_into_bar:
                    beat = st - bar_start + 1 if begins_here else 1
                    chord = {"root": s.root, "type": s.chord_type} if s.has_chord else None
                    slots.append({"beat": beat, "chord": chord})
            measures.append({"id": bar, "slots": slots})
        return {
            "name": self.name, "tonalCenter": self.key, "timeSignature": self.time_signature,
            "tempo": self.tempo, "measures": measures,
            "studio": {"neck": self.neck_name, "steps": [s.to_dict() for s in self.steps]},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StudioProgression":
        prog = cls(
            name=data.get("name", "Untitled progression"),
            key=data.get("tonalCenter", "C").rstrip("m") or "C",
            time_signature=data.get("timeSignature", "4/4") if data.get("timeSignature") in TIME_SIGNATURES else "4/4",
            tempo=int(data.get("tempo", 100)),
        )
        studio = data.get("studio")
        if studio and isinstance(studio.get("steps"), list):
            prog.steps = [StudioStep.from_dict(d) for d in studio["steps"]]
            prog.neck_name = studio.get("neck", "")
            return prog
        prog.steps = steps_from_chord_progression(ChordProgression.from_dict(data), prog.beats_per_bar)
        return prog


def steps_from_chord_progression(cp: ChordProgression, bpb: int) -> List[StudioStep]:
    """Each chord lasts until the next chord slot in its bar, or to the bar end; empty bars are rests."""
    steps: List[StudioStep] = []
    for m in cp.measures:
        chords = sorted((s.beat, s.root, s.chord_type) for s in m.slots if s.root and s.chord_type)
        if not chords:
            steps.append(StudioStep(beats=bpb))
            continue
        if chords[0][0] > 1:
            steps.append(StudioStep(beats=chords[0][0] - 1))
        for k, (beat, root, ctype) in enumerate(chords):
            end = chords[k + 1][0] if k + 1 < len(chords) else bpb + 1
            steps.append(StudioStep(root=root, chord_type=ctype, beats=max(1, min(bpb + 1, end) - beat)))
    return steps


# ---- typed chords ----------------------------------------------------------------------------

_SUFFIX_TO_TYPE = {v: k for k, v in CHORD_SYMBOL_SUFFIX.items()}
_EXTRA_SUFFIXES = {"Δ": "Major 7th", "Δ7": "Major 7th", "^7": "Major 7th", "°": "Diminished",
                   "o": "Diminished", "o7": "Diminished 7th", "ø": "Half-Diminished", "ø7": "Half-Diminished",
                   "-7b5": "Half-Diminished", "m": "Minor", "-": "Minor", "mi": "Minor", "mi7": "Minor 7th"}
_CHORD_RE = re.compile(r"^([A-Ga-g])([#b♯♭]?)(.*)$")
REST_TOKENS = {"-", "x", "n.c.", "nc", "rest"}


def parse_chord_symbol(text: str) -> Tuple[str, str]:
    """'Am7' -> ('A', 'Minor 7th'); 'F#m7b5', 'Bbmaj7', 'C+', 'Edim7', 'G/B' (bass ignored)."""
    raw = text.strip()
    head, slash, bass = raw.rpartition("/")
    if slash and head and re.fullmatch(r"[A-Ga-g][#b♯♭]?", bass):
        raw = head  # slash chord: the bass note is ignored ("6/9" is a chord type, not a bass)
    m = _CHORD_RE.match(raw)
    if not m:
        raise ValueError(f"Not a chord: {text!r}")
    letter, acc, suffix = m.groups()
    root = letter.upper() + {"♯": "#", "♭": "b"}.get(acc, acc)
    if root not in NOTE_TO_SEMITONE:
        raise ValueError(f"Unknown root in {text!r}")
    suffix = suffix.strip()
    ctype = _SUFFIX_TO_TYPE.get(suffix) or _EXTRA_SUFFIXES.get(suffix)
    if ctype is None:
        try:
            ctype = normalize_chord_type(suffix)
        except UnknownChordTypeError:
            raise ValueError(f"Unknown chord type in {text!r}") from None
    return root, ctype


def parse_progression_text(text: str, bpb: int = 4) -> List[StudioStep]:
    """Chord text -> steps.

    - Without bars, each chord is one bar: 'G C D7 G'. Add ':beats' for other lengths: 'Am7:2 D7:2'.
    - With bars, chords in a bar share it evenly: '| G | C | Am D7 | G |'.
    - '%' repeats the previous chord, '-' or 'N.C.' is a rest.
    """
    steps: List[StudioStep] = []

    def make(token: str, beats: int) -> StudioStep:
        tok, _, dur = token.partition(":")
        beats = int(dur) if dur.strip().isdigit() else beats
        if tok.strip().lower() in REST_TOKENS:
            return StudioStep(beats=max(1, beats))
        if tok.strip() == "%":
            if not steps or not steps[-1].has_chord:
                raise ValueError("'%' needs a chord before it")
            prev = steps[-1]
            return StudioStep(root=prev.root, chord_type=prev.chord_type, beats=max(1, beats))
        root, ctype = parse_chord_symbol(tok)
        return StudioStep(root=root, chord_type=ctype, beats=max(1, beats))

    if "|" in text:
        for bar in text.split("|"):
            tokens = bar.split()
            if not tokens:
                continue
            explicit = any(":" in t for t in tokens)
            base, extra = divmod(bpb, len(tokens))
            for i, tok in enumerate(tokens):
                beats = bpb if explicit else max(1, base + (1 if i < extra else 0))
                steps.append(make(tok, beats))
    else:
        for tok in text.split():
            steps.append(make(tok, bpb))
    return steps


def format_progression_text(steps: List[StudioStep], bpb: int = 4) -> str:
    """Inverse of parse_progression_text (bar-less form): one token per step, ':n' when n != bpb."""
    out = []
    for s in steps:
        tok = (chord_symbol(respell(s.root), s.chord_type) if s.has_chord else (s.label.replace(" ", "") or "-"))
        if not s.has_chord and s.has_stance:
            tok = "-"  # an unnamed grip has no chord text
        out.append(tok if s.beats == bpb else f"{tok}:{s.beats}")
    return " ".join(out)


# ---- generated progressions ------------------------------------------------------------------

CADENCES: Dict[str, Tuple[str, List[Tuple[int, str]]]] = {
    "major_251": ("ii–V–I (major)", [(2, "Minor 7th"), (7, "Dominant 7th"), (0, "Major 7th"), (0, "Major 7th")]),
    "minor_251": ("iiø–V–i (minor)", [(2, "Half-Diminished"), (7, "Dominant 7th"), (0, "Minor 7th"), (0, "Minor 7th")]),
    "turnaround": ("iii–vi–ii–V turnaround", [(4, "Minor 7th"), (9, "Dominant 7th"), (2, "Minor 7th"), (7, "Dominant 7th")]),
    "pop": ("I–vi–IV–V", [(0, "Major"), (9, "Minor"), (5, "Major"), (7, "Major")]),
    "country": ("I–IV–I–V (country)", [(0, "Major"), (5, "Major"), (0, "Major"), (7, "Major")]),
    "blues12": ("12-bar blues", [(0, "Dominant 7th"), (5, "Dominant 7th"), (0, "Dominant 7th"), (0, "Dominant 7th"),
                                 (5, "Dominant 7th"), (5, "Dominant 7th"), (0, "Dominant 7th"), (0, "Dominant 7th"),
                                 (7, "Dominant 7th"), (5, "Dominant 7th"), (0, "Dominant 7th"), (7, "Dominant 7th")]),
}

_DICE_DEGREES = {1: (0, "Major"), 2: (2, "Minor 7th"), 3: (4, "Minor 7th"),
                 4: (5, "Major 7th"), 5: (7, "Dominant 7th"), 6: (9, "Minor 7th")}


def cadence_progression(kind: str, key: str, bpb: int = 4) -> StudioProgression:
    title, degrees = CADENCES[kind]
    key_pc = NOTE_TO_SEMITONE[key]
    steps = [StudioStep(root=spell_pc(key_pc + semis), chord_type=ctype, beats=bpb) for semis, ctype in degrees]
    return StudioProgression(name=f"{respell(key)} {title}", key=key, steps=steps)


def dice_progression(key: str, bpb: int = 4, rng: Optional[random.Random] = None) -> Tuple[StudioProgression, str]:
    """Two rolled diatonic degrees, each approached by its own V7 (the voice leader's dice game)."""
    rng = rng or random.Random()
    key_pc = NOTE_TO_SEMITONE[key]
    rolls = [rng.randint(1, 6), rng.randint(1, 6)]
    steps = []
    for die in rolls:
        semis, ctype = _DICE_DEGREES[die]
        target = (key_pc + semis) % 12
        steps.append(StudioStep(root=spell_pc(target + 7), chord_type="Dominant 7th", beats=bpb))
        steps.append(StudioStep(root=spell_pc(target), chord_type=ctype, beats=bpb))
    text = f"Rolled degrees {rolls[0]} and {rolls[1]}: " + " → ".join(s.symbol for s in steps)
    return StudioProgression(name=f"Dice {rolls[0]} & {rolls[1]} ({respell(key)})", key=key, steps=steps), text


def preset_progression(preset: ProgressionPreset, neck: Neck, bpb: int = 4) -> Optional[StudioProgression]:
    """A practice preset with its curated stances (pinned). None if the neck lacks a controller."""
    tab_steps = resolve_preset_steps(preset, neck)
    if tab_steps is None:
        return None
    steps = []
    for i, ts in enumerate(tab_steps):
        root, ctype = (preset.chords[i] if preset.chords and i < len(preset.chords) else (None, None))
        st = StudioStep(root=root, chord_type=ctype, beats=bpb, label="" if root else ts.chord_label)
        st.set_stance(ts.fret, ts.engaged_levers, ts.grip_strings, pinned=True)
        steps.append(st)
    return StudioProgression(name=preset.name, key=preset.key, steps=steps, neck_name=neck.name)


# ---- voice leading ---------------------------------------------------------------------------

def fill_stances(neck: Neck, steps: List[StudioStep], constraints: VoiceLeadingConstraints,
                 only_missing: bool = False) -> List[int]:
    """Voice-leads every chord step that is not pinned (only_missing: that has no stance yet).
    Pinned steps (and, with only_missing, voiced ones) are anchors: each run of free steps between
    them is solved on its own, starting near the anchor before it. Returns unsolvable step indices."""

    def is_anchor(s: StudioStep) -> bool:
        return s.has_stance and (s.pinned or only_missing or not s.has_chord)

    unsolved: List[int] = []
    segment: List[int] = []
    last_fret: Optional[int] = constraints.start_fret

    def flush():
        nonlocal segment
        if not segment:
            return
        prog = ChordProgression(name="studio", measures=[
            ProgressionMeasure(measure_id=k, slots=[ChordSlot(beat=1, root=steps[i].root, chord_type=steps[i].chord_type)])
            for k, i in enumerate(segment)
        ])
        result = VoiceLeadingEngine.solve_progression(neck, prog, replace(constraints, start_fret=last_fret))
        for i, v in zip(segment, result):
            if v is None:
                steps[i].clear_stance()
                unsolved.append(i)
            else:
                steps[i].set_stance(v.fret, v.engaged_levers, v.grip_strings, pinned=False)
        segment = []

    for i, s in enumerate(steps):
        if is_anchor(s):
            flush()
            last_fret = s.fret
        elif s.has_chord:
            segment.append(i)
    flush()
    return sorted(unsolved)


# ---- captured grips ----------------------------------------------------------------------------

_PREFERRED_TYPES = ["Major", "Minor", "Dominant 7th", "Minor 7th", "Major 7th", "Major 6th", "Minor 6th",
                    "Sus4", "Diminished", "Half-Diminished", "Diminished 7th", "Augmented"]


def identify_grip_chord(neck: Neck, fret: int, controllers, grip,
                        hint: Optional[Tuple[str, str]] = None) -> Optional[Tuple[str, str]]:
    """(root, chord type) the grip sounds, resolved on the neck. The hint (e.g. the harmonic target)
    wins when the grip fits it; otherwise the bass note is tried first as the root, exact matches
    before ones missing only the 5th. None for dyads or unrecognised grips."""
    grip = list(grip)
    pcs = grip_pitch_classes(neck, fret, controllers, grip)
    if not pcs or len(pcs) < 2:
        return None

    def tones(root_pc, ctype):
        return {(root_pc + k) % 12 for k in CHORD_FORMULAS[ctype]}

    if hint and hint[0] in NOTE_TO_SEMITONE and hint[1] in CHORD_FORMULAS:
        hpc = NOTE_TO_SEMITONE[hint[0]]
        if pcs <= tones(hpc, hint[1]) and hpc in pcs:
            return hint
    if len(pcs) < 3:
        return None
    states = {s.string_number: s for s in FretboardResolver.resolve_neck_state(neck, fret, set(controllers))}
    bass_pc = states[max(grip)].pitch_class if max(grip) in states else None
    roots = ([bass_pc] if bass_pc in pcs else []) + sorted(pc for pc in pcs if pc != bass_pc)
    types = _PREFERRED_TYPES + [t for t in CHORD_FORMULAS if t not in _PREFERRED_TYPES]
    for exact in (True, False):
        for rpc in roots:
            for ctype in types:
                t = tones(rpc, ctype)
                if exact and t == pcs:
                    return spell_pc(rpc), ctype
                if not exact and pcs < t and t - pcs <= {(rpc + 7) % 12}:
                    return spell_pc(rpc), ctype
    return None


# ---- playback and tab ------------------------------------------------------------------------

def arpeggio_strings(step: StudioStep, beats: Optional[int] = None) -> List[int]:
    """String order for STYLE_ARPEGGIO: the Franklin permutation, one cycle per beat."""
    if not step.grip:
        return []
    events = PermutationEngine.generate_sequence(step.perm_id, list(step.grip), cycles=max(1, beats or step.beats))
    return [e.string_number for e in events]


def tab_steps(steps: List[StudioStep], names: Dict[str, str]) -> List[TabStep]:
    """Voiced steps as TabSteps (controllers shown by display name). Arpeggios expand to one column per
    note of a single permutation cycle, with the pick finger."""
    out: List[TabStep] = []
    for s in steps:
        if not s.has_stance:
            continue
        ctrl_names = [names.get(c, c) for c in s.controllers]
        if s.style == STYLE_ARPEGGIO:
            for k, ev in enumerate(PermutationEngine.generate_sequence(s.perm_id, list(s.grip), cycles=1)):
                out.append(TabStep(fret=s.fret, engaged_levers=list(ctrl_names), grip_strings={ev.string_number},
                                   chord_label=s.symbol if k == 0 else "", pick_finger=ev.finger))
        else:
            out.append(TabStep(fret=s.fret, engaged_levers=list(ctrl_names), grip_strings=set(s.grip),
                               chord_label=s.symbol))
    return out


@dataclass
class BeatEvent:
    accent: bool                 # first beat of a bar (or of a count-in bar)
    count_in: bool
    step: Optional[int]          # step index starting on this beat
    done: bool                   # past the end (no loop): stop


@dataclass
class PlaybackPlan:
    """What happens on each beat k (k = 0 is the moment Play is pressed). Steps first..last are
    played; with loop they repeat without the count-in."""
    starts: Dict[int, int]       # beat offset in the range -> step index
    length: int                  # beats in the played range
    range_start: int             # absolute beat of the range start (bar accents follow the song)
    bpb: int
    count_in: int                # beats
    loop: bool

    @classmethod
    def build(cls, prog: StudioProgression, first: int, last: int, count_in_bars: int, loop: bool) -> "PlaybackPlan":
        starts = prog.step_starts()
        first = max(0, min(first, len(prog.steps) - 1))
        last = max(first, min(last, len(prog.steps) - 1))
        base = starts[first]
        offsets = {starts[i] - base: i for i in range(first, last + 1)}
        length = starts[last] + prog.steps[last].beats - base
        bpb = prog.beats_per_bar
        return cls(offsets, length, base, bpb, max(0, count_in_bars) * bpb, loop)

    def at(self, k: int) -> BeatEvent:
        if k < self.count_in:
            return BeatEvent(accent=k % self.bpb == 0, count_in=True, step=None, done=False)
        rel = k - self.count_in
        if rel >= self.length and not self.loop:
            return BeatEvent(accent=False, count_in=False, step=None, done=True)
        rel %= max(1, self.length)
        return BeatEvent(accent=(self.range_start + rel) % self.bpb == 0, count_in=False,
                         step=self.starts.get(rel), done=False)
