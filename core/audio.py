"""Low-latency native MIDI audio engine for pedal steel with natural acoustic sustain (Patch 25),
channel-per-string independent mechanical pitch glides, and Jeff Newman compensated temperament.

Channel map (D-01): strings use channels 0-8 and 10-14 (channel 9 is the General MIDI percussion
channel and is never used); channel 15 is reserved for sequences and single clicked notes.
"""

import ctypes
import logging
import math
import sys
import threading
import time
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Union

if TYPE_CHECKING:  # pragma: no cover
    from core.models import Neck

log = logging.getLogger(__name__)

if sys.platform == "win32":
    winmm = ctypes.windll.winmm
else:
    winmm = None

STRING_CHANNELS: List[int] = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14]
SEQUENCE_CHANNEL = 15
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


def cents_to_bend(cents: float) -> int:
    """Pitch-bend value for a cents offset, assuming the GM default +/-2 semitone bend range."""
    return int(max(-8192, min(8191, (cents / 200.0) * 8191)))


class MidiAudioEngine:
    def __init__(self):
        self._opened = False
        self._hmidi = ctypes.c_void_p()
        self._lock = threading.Lock()          # serializes winmm calls
        self._state_lock = threading.Lock()    # guards _active_pitches / _current_bends
        self._active_pitches: Dict[int, int] = {}       # channel -> sounding midi pitch
        self._current_bends: Dict[int, int] = {}        # channel -> bend (-8192 to 8191)
        self.use_compensated_temperament: bool = False

        if sys.platform == "win32" and winmm is not None:
            try:
                res = winmm.midiOutOpen(ctypes.byref(self._hmidi), ctypes.c_uint(0xFFFFFFFF), 0, 0, 0)
                if res != 0:
                    res = winmm.midiOutOpen(ctypes.byref(self._hmidi), 0, 0, 0, 0)

                if res == 0 and self._hmidi.value:
                    self._opened = True
                    for ch in ALL_CHANNELS:
                        # GM Patch 25: Steel String Acoustic Guitar
                        self._send_short_msg(0x000019C0 | ch)
                        # CC 64 (Sustain Pedal ON)
                        self._send_short_msg(0x007F40B0 | ch)
                        self._set_channel_pitch_bend(ch, 0)
                else:
                    log.warning("MIDI output could not be opened (midiOutOpen=%s)", res)
            except Exception:
                log.exception("MIDI initialisation failed")
                self._opened = False

    def _send_short_msg(self, msg: int):
        if self._opened and self._hmidi and self._hmidi.value:
            with self._lock:
                try:
                    winmm.midiOutShortMsg(self._hmidi, ctypes.c_uint32(msg))
                except Exception:
                    log.debug("midiOutShortMsg failed", exc_info=True)

    def _set_channel_pitch_bend(self, channel: int, bend_val: int):
        """Sends 14-bit pitch bend to a channel. bend_val: -8192..8191 (+/-2 semitones). 0 is center."""
        ch = max(0, min(15, channel))
        val_14bit = max(0, min(16383, int(bend_val + 8192)))
        lsb = val_14bit & 0x7F
        msb = (val_14bit >> 7) & 0x7F
        self._send_short_msg((0xE0 | ch) | (lsb << 8) | (msb << 16))
        with self._state_lock:
            self._current_bends[ch] = bend_val

    def _strike(self, ch: int, pitch: int, velocity: int, bend: int):
        """Note-off for the channel's previous note, set bend, note-on."""
        with self._state_lock:
            prior = self._active_pitches.get(ch)
        if prior is not None:
            self._send_short_msg((0x80 | ch) | ((prior & 0x7F) << 8))
        self._set_channel_pitch_bend(ch, bend)
        self._send_short_msg((0x90 | ch) | ((int(pitch) & 0x7F) << 8) | ((velocity & 0x7F) << 16))
        with self._state_lock:
            self._active_pitches[ch] = int(pitch)

    def silence_all(self):
        if not self._opened:
            return
        for ch in ALL_CHANNELS:
            self._send_short_msg(0x000078B0 | ch)  # All Sound Off
            self._send_short_msg(0x00007BB0 | ch)  # All Notes Off
            self._send_short_msg(0x007F40B0 | ch)  # Sustain On
            self._set_channel_pitch_bend(ch, 0)
        with self._state_lock:
            self._active_pitches.clear()
            self._current_bends.clear()

    def play_note(
        self,
        pitch: int,
        string_num: Optional[int] = None,
        velocity: int = 95,
        cents_offset: float = 0.0,
    ):
        """Plays one note on its string's channel (or the sequence channel if no string is given)."""
        if not self._opened or pitch <= 0:
            return
        ch = channel_for_string(string_num) if string_num else SEQUENCE_CHANNEL
        bend = cents_to_bend(cents_offset) if self.use_compensated_temperament else 0
        threading.Thread(target=self._strike, args=(ch, pitch, velocity, bend), daemon=True).start()

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
        if not pitch_dict:
            return
        cents = cents or {}
        use_cents = self.use_compensated_temperament

        def _worker():
            # Stagger lowest bass string to highest treble string
            ordered_strings = sorted(pitch_dict.keys(), reverse=True)
            for idx, s_num in enumerate(ordered_strings):
                bend = cents_to_bend(cents.get(s_num, 0.0)) if use_cents else 0
                self._strike(channel_for_string(s_num), pitch_dict[s_num], velocity, bend)
                if roll and idx < len(ordered_strings) - 1:
                    time.sleep(0.045)

        threading.Thread(target=_worker, daemon=True).start()

    def glide_string_pitch(
        self,
        string_num: int,
        target_midi: int,
        semitone_delta: float,
        duration_sec: float = 0.080,
    ):
        """Smooth mechanical pull glide on an individual string channel without re-striking the note.
        (Not wired into the UI yet; see docs/architecture/07-enhancements.md E-11.)"""
        if not self._opened:
            return

        ch = channel_for_string(string_num)
        target_bend = int(max(-8191, min(8191, (semitone_delta / 2.0) * 8191)))

        def _glide_worker():
            steps = 16
            sleep_step = max(0.003, duration_sec / steps)
            with self._state_lock:
                start_bend = self._current_bends.get(ch, 0)

            for i in range(1, steps + 1):
                fraction = i / steps
                curve = 0.5 - 0.5 * math.cos(fraction * math.pi)
                self._set_channel_pitch_bend(ch, int(start_bend + (target_bend - start_bend) * curve))
                time.sleep(sleep_step)

            self._set_channel_pitch_bend(ch, target_bend)

        threading.Thread(target=_glide_worker, daemon=True).start()

    def play_scale_sequence(self, pitches: List[int], delay: float = 0.38, velocity: int = 95):
        """Plays notes one after another on the sequence channel, releasing each previous note."""
        if not self._opened or not pitches:
            return

        valid_pitches = [int(p) for p in pitches if p > 0]
        if not valid_pitches:
            return

        def _worker():
            ch = SEQUENCE_CHANNEL
            for p in valid_pitches:
                self._strike(ch, p, velocity, 0)
                time.sleep(delay)
            with self._state_lock:
                last = self._active_pitches.pop(ch, None)
            if last is not None:
                self._send_short_msg((0x80 | ch) | ((last & 0x7F) << 8))

        threading.Thread(target=_worker, daemon=True).start()

    def set_compensated_temperament(self, enabled: bool):
        self.use_compensated_temperament = bool(enabled)

    def close(self):
        if self._opened and self._hmidi and self._hmidi.value:
            try:
                for ch in ALL_CHANNELS:
                    self._send_short_msg(0x000040B0 | ch)  # Sustain off
                winmm.midiOutReset(self._hmidi)
                winmm.midiOutClose(self._hmidi)
            except Exception:
                log.debug("MIDI close failed", exc_info=True)
            self._opened = False
            self._hmidi = None
