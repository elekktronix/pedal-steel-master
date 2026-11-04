"""Low-latency native MIDI audio engine for pedal steel with natural acoustic sustain (Patch 25),
channel-per-string independent mechanical pitch glides, and Jeff Newman compensated temperament.

All MIDI output runs on one scheduler thread fed by a timed queue (E-11).

Channel map (D-01): strings use channels 0-8 and 10-14 (channel 9 is the General MIDI percussion
channel and is never used); channel 15 is reserved for sequences and single clicked notes.
"""

import ctypes
import heapq
import itertools
import logging
import math
import sys
import threading
import time
from typing import TYPE_CHECKING, Callable, Dict, Iterable, List, Optional, Tuple, Union

if TYPE_CHECKING:  # pragma: no cover
    from core.models import Neck

log = logging.getLogger(__name__)

if sys.platform == "win32":
    winmm = ctypes.windll.winmm
else:
    winmm = None

STRING_CHANNELS: List[int] = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14]
SEQUENCE_CHANNEL = 15
PERCUSSION_CHANNEL = 9  # GM drums: metronome clicks only, never a string

# Metronome click sounds: name -> (accent GM drum note, normal GM drum note)
CLICK_SOUNDS: Dict[str, Tuple[int, int]] = {
    "Woodblock": (76, 77),
    "Claves": (75, 75),
    "Side Stick": (37, 37),
    "Cowbell": (56, 56),
    "Closed Hi-Hat": (42, 42),
    "Metronome Bell": (34, 33),
}
ALL_CHANNELS: List[int] = STRING_CHANNELS + [SEQUENCE_CHANNEL]


def channel_for_string(string_num: int) -> int:
    """MIDI channel for a string (never the percussion channel 9; unique for up to 14 strings)."""
    return STRING_CHANNELS[(int(string_num) - 1) % len(STRING_CHANNELS)]


# Jeff Newman Master Temperament Table (Cents) for the standard 10-string E9 tuning.
# Controllers are keyed by functional role (core.stances), not by controller ID.
NEWMAN_CENTS_OFFSETS: Dict[str, Dict] = {
    "open_strings": {
        1: 6.0,    # F#4 (+6 cents)
        2: -4.0,   # D#4 (-4 cents)
        3: -4.0,   # G#4 (-4 cents)
        4: 10.0,   # E4  (+10 cents)
        5: 8.0,    # B3  (+8 cents)
        6: -4.0,   # G#3 (-4 cents)
        7: 6.0,    # F#3 (+6 cents)
        8: 10.0,   # E3  (+10 cents)
        9: 6.0,    # D3  (+6 cents)
        10: 8.0,   # B2  (+8 cents)
    },
    "controllers": {
        "A": -6.0,   # Pedal A (C#) (-6 cents)
        "B": 4.0,    # Pedal B (A)  (+4 cents)
        "C": -2.0,   # Pedal C (F#) (-2 cents)
        "F": -18.0,  # F Lever (F)  (-18 cents)
        "D": 2.0,    # D Lever (Eb) (+2 cents)
    },
}

# Pitch classes of the standard 10-string E9 open tuning, strings 1..10.
_E9_OPEN_PCS = [6, 3, 8, 4, 11, 8, 6, 4, 2, 11]


def compute_newman_cents(neck: "Neck", engaged: Iterable[str], strings: Iterable[int]) -> Dict[int, float]:
    """Cents offsets per string for Jeff Newman's compensated tuning (D-19).

    Applies only to a 10-string neck in standard E9 open tuning; returns {} otherwise. A string
    pulled by a fully engaged controller with a known role uses that controller's offset; a string
    pulled by any other controller (or a half-stop) is left at 0 (equal temperament); an unpulled
    string uses its open-string offset.
    """
    if neck is None or neck.string_count != 10:
        return {}
    pcs = [sp.midi_note % 12 for sp in sorted(neck.open_tuning, key=lambda s: s.string_number)]
    if pcs != _E9_OPEN_PCS:
        return {}

    from core.stances import detect_roles

    role_of = {cid: role for role, cid in detect_roles(neck).items()}
    controllers = {**neck.pedals, **neck.knee_levers}
    cents: Dict[int, float] = {}
    for s_num in strings:
        pulling = [
            tok for tok in engaged
            if tok.replace("_HALF", "") in controllers
            and controllers[tok.replace("_HALF", "")].changes.get(s_num, 0) != 0
        ]
        if not pulling:
            cents[s_num] = NEWMAN_CENTS_OFFSETS["open_strings"].get(s_num, 0.0)
            continue
        offset = 0.0
        for tok in pulling:
            if tok.endswith("_HALF"):
                continue
            role = role_of.get(tok)
            if role in NEWMAN_CENTS_OFFSETS["controllers"]:
                offset = NEWMAN_CENTS_OFFSETS["controllers"][role]
                break
        cents[s_num] = offset
    return cents


BEND_RANGE_SEMITONES = 2.0  # General MIDI default pitch-bend sensitivity


def cents_to_bend(cents: float) -> int:
    """Pitch-bend value for a cents offset, assuming the GM default +/-2 semitone bend range."""
    return int(max(-8192, min(8191, (cents / (BEND_RANGE_SEMITONES * 100.0)) * 8191)))


class _Scheduler(threading.Thread):
    """Single worker thread executing timed MIDI actions in order (E-11).

    All MIDI output and all engine state changes happen on this thread, so no per-note threads
    are created and no state is shared across threads.
    """

    def __init__(self):
        super().__init__(name="psg-midi-scheduler", daemon=True)
        self._cond = threading.Condition()
        self._queue: List[tuple] = []
        self._seq = itertools.count()
        self._running = True

    def schedule(self, delay: float, fn: Callable[[], None]) -> None:
        with self._cond:
            heapq.heappush(self._queue, (time.monotonic() + max(0.0, delay), next(self._seq), fn))
            self._cond.notify()

    def stop(self, timeout: float = 1.0) -> None:
        with self._cond:
            self._running = False
            self._cond.notify()
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout)

    def run(self) -> None:
        while True:
            with self._cond:
                while self._running and not self._queue:
                    self._cond.wait()
                if not self._running:
                    return
                due, _, fn = self._queue[0]
                wait = due - time.monotonic()
                if wait > 0:
                    self._cond.wait(wait)
                    continue
                heapq.heappop(self._queue)
            try:
                fn()
            except Exception:
                log.exception("MIDI scheduler action failed")

    def drain(self, timeout: float = 2.0) -> None:
        """Blocks until the queue is empty (used by tests and shutdown)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._cond:
                if not self._queue:
                    break
            time.sleep(0.005)
        time.sleep(0.01)  # let the last popped action finish


class MidiAudioEngine:
    """Pedal steel MIDI voice engine.

    `send` lets callers (and tests) inject a function receiving raw short MIDI messages; by
    default the Windows MIDI mapper (winmm) is used, and on other platforms the engine is silent.
    """

    GLIDE_STEPS = 16

    def __init__(self, send: Optional[Callable[[int], None]] = None):
        self._opened = False
        self._hmidi = ctypes.c_void_p()
        self._send_fn: Optional[Callable[[int], None]] = None
        # Worker-thread state (only touched on the scheduler thread):
        self._active_pitches: Dict[int, int] = {}   # channel -> sounding midi pitch
        self._current_bends: Dict[int, int] = {}    # channel -> bend (-8192 to 8191)
        self._glide_gen: Dict[int, int] = {}        # channel -> generation; newer strikes/glides cancel older glides
        self.use_compensated_temperament: bool = False

        if send is not None:
            self._send_fn = send
            self._opened = True
        elif sys.platform == "win32" and winmm is not None:
            try:
                res = winmm.midiOutOpen(ctypes.byref(self._hmidi), ctypes.c_uint(0xFFFFFFFF), 0, 0, 0)
                if res != 0:
                    res = winmm.midiOutOpen(ctypes.byref(self._hmidi), 0, 0, 0, 0)
                if res == 0 and self._hmidi.value:
                    self._send_fn = lambda msg: winmm.midiOutShortMsg(self._hmidi, ctypes.c_uint32(msg))
                    self._opened = True
                else:
                    log.warning("MIDI output could not be opened (midiOutOpen=%s)", res)
            except Exception:
                log.exception("MIDI initialisation failed")
                self._opened = False

        self._scheduler = _Scheduler()
        self._scheduler.start()
        if self._opened:
            self._scheduler.schedule(0, self._init_channels)

    # ---- worker-thread primitives -------------------------------------------------------------
    def _send(self, msg: int) -> None:
        if self._opened and self._send_fn is not None:
            try:
                self._send_fn(msg)
            except Exception:
                log.debug("MIDI send failed", exc_info=True)

    def _init_channels(self) -> None:
        for ch in ALL_CHANNELS:
            self._send(0x000019C0 | ch)  # GM Patch 25: Steel String Acoustic Guitar
            self._send(0x007F40B0 | ch)  # CC 64 (Sustain Pedal ON)
            self._bend(ch, 0)

    def _bend(self, channel: int, bend_val: int) -> None:
        """14-bit pitch bend on a channel. bend_val: -8192..8191 (+/-2 semitones). 0 is center."""
        ch = max(0, min(15, channel))
        val_14bit = max(0, min(16383, int(bend_val + 8192)))
        self._send((0xE0 | ch) | ((val_14bit & 0x7F) << 8) | (((val_14bit >> 7) & 0x7F) << 16))
        self._current_bends[ch] = bend_val

    def _note_off(self, ch: int) -> None:
        prior = self._active_pitches.pop(ch, None)
        if prior is not None:
            self._send((0x80 | ch) | ((prior & 0x7F) << 8))

    def _strike(self, ch: int, pitch: int, velocity: int, bend: int) -> None:
        """Note-off for the channel's previous note, cancel its glide, set bend, note-on."""
        self._glide_gen[ch] = self._glide_gen.get(ch, 0) + 1
        self._note_off(ch)
        self._bend(ch, bend)
        self._send((0x90 | ch) | ((int(pitch) & 0x7F) << 8) | ((velocity & 0x7F) << 16))
        self._active_pitches[ch] = int(pitch)

    # ---- public API (thread-safe: everything is queued) ---------------------------------------
    @property
    def is_available(self) -> bool:
        return self._opened

    def silence_all(self):
        if not self._opened:
            return

        def _do():
            for ch in ALL_CHANNELS:
                self._glide_gen[ch] = self._glide_gen.get(ch, 0) + 1
                self._send(0x000078B0 | ch)  # All Sound Off
                self._send(0x00007BB0 | ch)  # All Notes Off
                self._send(0x007F40B0 | ch)  # Sustain On
                self._bend(ch, 0)
            self._active_pitches.clear()

        self._scheduler.schedule(0, _do)

    def play_note(
        self,
        pitch: int,
        string_num: Optional[int] = None,
        velocity: int = 95,
        cents_offset: float = 0.0,
        delay: float = 0.0,
    ):
        """Plays one note on its string's channel (or the sequence channel if no string is given),
        `delay` seconds from now (queued on the scheduler, so spacing is exact)."""
        if not self._opened or pitch <= 0:
            return
        ch = channel_for_string(string_num) if string_num else SEQUENCE_CHANNEL
        bend = cents_to_bend(cents_offset) if self.use_compensated_temperament else 0
        self._scheduler.schedule(delay, lambda: self._strike(ch, pitch, velocity, bend))

    def play_pocket(
        self,
        pitches: Union[List[int], Dict[int, int]],
        roll: bool = False,
        velocity: int = 95,
        cents: Optional[Dict[int, float]] = None,
    ):
        """Plays a grip. Pass a dict {string_number: midi} so every note uses its own string channel.
        (A list is still accepted and mapped to strings 1..n by position.)"""
        if not self._opened or not pitches:
            return
        if isinstance(pitches, dict):
            pitch_dict = {int(k): int(v) for k, v in pitches.items() if v > 0}
        elif isinstance(pitches, list):
            pitch_dict = {idx + 1: int(p) for idx, p in enumerate(pitches) if p > 0}
        else:
            return
        cents = cents or {}
        use_cents = self.use_compensated_temperament

        # Stagger lowest bass string to highest treble string when rolling.
        for idx, s_num in enumerate(sorted(pitch_dict, reverse=True)):
            ch = channel_for_string(s_num)
            bend = cents_to_bend(cents.get(s_num, 0.0)) if use_cents else 0
            pitch = pitch_dict[s_num]
            self._scheduler.schedule(
                idx * 0.045 if roll else 0.0,
                lambda ch=ch, pitch=pitch, bend=bend: self._strike(ch, pitch, velocity, bend),
            )

    def glide_string_pitch(
        self,
        string_num: int,
        semitone_delta: float,
        duration_sec: float = 0.12,
        cents_offset: float = 0.0,
    ) -> bool:
        """Bends the note sounding on a string to `semitone_delta` (+ cents) above its struck pitch
        without re-striking it: a pedal/lever "swell" (E-11). Returns False if the target is outside
        the +/-2 semitone bend range (callers should re-strike instead). A newer glide or strike on
        the same string cancels this one."""
        if not self._opened:
            return False
        total_cents = semitone_delta * 100.0 + (cents_offset if self.use_compensated_temperament else 0.0)
        if abs(total_cents) > BEND_RANGE_SEMITONES * 100.0:
            return False
        ch = channel_for_string(string_num)
        target = cents_to_bend(total_cents)
        steps = self.GLIDE_STEPS
        step_time = max(0.003, duration_sec / steps)

        def _start():
            gen = self._glide_gen.get(ch, 0) + 1
            self._glide_gen[ch] = gen
            start = self._current_bends.get(ch, 0)
            for i in range(1, steps + 1):
                curve = 0.5 - 0.5 * math.cos((i / steps) * math.pi)  # mechanical ease in/out
                value = int(start + (target - start) * curve)
                self._scheduler.schedule(
                    i * step_time,
                    lambda value=value: self._bend(ch, value) if self._glide_gen.get(ch) == gen else None,
                )

        self._scheduler.schedule(0, _start)
        return True

    def play_click(self, accent: bool = False, sound: str = "Woodblock", velocity: int = 110, delay: float = 0.0):
        """Metronome click on the GM percussion channel. It goes through the same scheduler as the
        notes, so a click and a note queued together sound together (unlike a sound-card sample)."""
        if not self._opened:
            return
        hi, lo = CLICK_SOUNDS.get(sound, CLICK_SOUNDS["Woodblock"])
        note = hi if accent else lo
        vel = min(127, velocity + 15) if accent else velocity
        ch = PERCUSSION_CHANNEL
        self._scheduler.schedule(delay, lambda: self._send((0x90 | ch) | (note << 8) | (vel << 16)))
        self._scheduler.schedule(delay + 0.08, lambda: self._send((0x80 | ch) | (note << 8)))

    def play_scale_sequence(self, pitches: List[int], delay: float = 0.38, velocity: int = 95):
        """Plays notes one after another on the sequence channel, releasing each previous note."""
        if not self._opened or not pitches:
            return
        valid = [int(p) for p in pitches if p > 0]
        ch = SEQUENCE_CHANNEL
        for i, p in enumerate(valid):
            self._scheduler.schedule(i * delay, lambda p=p: self._strike(ch, p, velocity, 0))
        if valid:
            self._scheduler.schedule(len(valid) * delay, lambda: self._note_off(ch))

    def set_compensated_temperament(self, enabled: bool):
        self.use_compensated_temperament = bool(enabled)

    def wait_idle(self, timeout: float = 2.0) -> None:
        """Waits until all queued MIDI actions have run (tests / shutdown)."""
        self._scheduler.drain(timeout)

    def close(self):
        if self._opened:
            def _sustain_off():
                for ch in ALL_CHANNELS:
                    self._send(0x000040B0 | ch)

            self._scheduler.schedule(0, _sustain_off)
            self._scheduler.drain(0.5)
        self._scheduler.stop()
        if self._opened and self._hmidi and self._hmidi.value and self._send_fn is not None and winmm is not None:
            try:
                winmm.midiOutReset(self._hmidi)
                winmm.midiOutClose(self._hmidi)
            except Exception:
                log.debug("MIDI close failed", exc_info=True)
        self._opened = False
        self._hmidi = None
