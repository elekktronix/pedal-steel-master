"""Low-latency native MIDI audio engine for pedal steel with natural acoustic sustain (Patch 25),
channel-per-string independent mechanical pitch glides, and Jeff Newman compensated temperament.
"""

import ctypes
import math
import sys
import threading
import time
from typing import Dict, List, Optional, Set, Union

if sys.platform == "win32":
    winmm = ctypes.windll.winmm
else:
    winmm = None

# Jeff Newman Master Temperament Table (Cents)
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
        "P1": -6.0,   # Pedal A (C#) (-6 cents)
        "P2": 4.0,    # Pedal B (A)  (+4 cents)
        "P3": -2.0,   # Pedal C (F#) (-2 cents)
        "LKL": -18.0, # F Lever (F)  (-18 cents)
        "LKR": 2.0,   # D Lever (Eb) (+2 cents)
    }
}


class MidiAudioEngine:
    def __init__(self):
        self._opened = False
        self._hmidi = ctypes.c_void_p()
        self._lock = threading.Lock()
        self._active_pitches: Dict[int, int] = {}       # string_num -> current midi pitch
        self._current_bends: Dict[int, int] = {}        # channel -> bend (-8192 to 8191)
        self.use_compensated_temperament: bool = False

        if sys.platform == "win32" and winmm is not None:
            try:
                res = winmm.midiOutOpen(ctypes.byref(self._hmidi), ctypes.c_uint(0xFFFFFFFF), 0, 0, 0)
                if res != 0:
                    res = winmm.midiOutOpen(ctypes.byref(self._hmidi), 0, 0, 0, 0)

                if res == 0 and self._hmidi.value:
                    self._opened = True
                    # Initialize 10 string channels (0-9)
                    for ch in range(10):
                        # GM Patch 25: Steel String Acoustic Guitar on all channels
                        self._send_short_msg(0x000019C0 | ch)
                        # CC 64 (Sustain Pedal ON) on all channels
                        self._send_short_msg(0x007F40B0 | ch)
                        self._set_channel_pitch_bend(ch, 0)
                        self._current_bends[ch] = 0
            except Exception:
                self._opened = False

    def _send_short_msg(self, msg: int):
        if self._opened and self._hmidi and self._hmidi.value:
            with self._lock:
                try:
                    winmm.midiOutShortMsg(self._hmidi, ctypes.c_uint32(msg))
                except Exception:
                    pass

    def _set_channel_pitch_bend(self, channel: int, bend_val: int):
        """Sends 14-bit pitch bend to a specific string channel.
        bend_val: -8192 (down 2 semitones) to +8191 (up 2 semitones). 0 is center.
        """
        ch = max(0, min(15, channel))
        val_14bit = max(0, min(16383, int(bend_val + 8192)))
        lsb = val_14bit & 0x7F
        msb = (val_14bit >> 7) & 0x7F
        pb_msg = (0xE0 | ch) | (lsb << 8) | (msb << 16)
        self._send_short_msg(pb_msg)
        self._current_bends[ch] = bend_val

    def silence_all(self):
        if not self._opened:
            return
        for ch in range(10):
            self._send_short_msg(0x000078B0 | ch)  # All Sound Off
            self._send_short_msg(0x00007BB0 | ch)  # All Notes Off
            self._send_short_msg(0x007F40B0 | ch)  # Sustain On
            self._set_channel_pitch_bend(ch, 0)
        self._active_pitches.clear()
        self._current_bends.clear()

    def play_note(self, pitch: int, string_num: int = 1, velocity: int = 95, cents_offset: float = 0.0):
        if not self._opened or pitch <= 0:
            return

        ch = (string_num - 1) % 10

        def _worker():
            prior = self._active_pitches.get(string_num)
            if prior is not None:
                note_off = (0x80 | ch) | ((prior & 0x7F) << 8)
                self._send_short_msg(note_off)

            wheel_val = 0
            if self.use_compensated_temperament and cents_offset != 0.0:
                wheel_val = int((cents_offset / 200.0) * 8191)

            self._set_channel_pitch_bend(ch, wheel_val)

            note_on = (0x90 | ch) | ((int(pitch) & 0x7F) << 8) | ((velocity & 0x7F) << 16)
            self._send_short_msg(note_on)
            self._active_pitches[string_num] = int(pitch)

        threading.Thread(target=_worker, daemon=True).start()

    def play_pocket(self, pitches: Union[List[int], Dict[int, int]], roll: bool = False, velocity: int = 95):
        if not self._opened or not pitches:
            return

        # Normalize to string_number -> pitch
        if isinstance(pitches, dict):
            pitch_dict = {int(k): int(v) for k, v in pitches.items() if v > 0}
        elif isinstance(pitches, list):
            pitch_dict = {idx + 1: int(p) for idx, p in enumerate(pitches) if p > 0}
        else:
            return

        if not pitch_dict:
            return

        def _worker():
            # Stagger lowest bass string to highest treble string
            ordered_strings = sorted(pitch_dict.keys(), reverse=True)
            for idx, s_num in enumerate(ordered_strings):
                p = pitch_dict[s_num]
                ch = (s_num - 1) % 10

                prior = self._active_pitches.get(s_num)
                if prior is not None:
                    note_off = (0x80 | ch) | ((prior & 0x7F) << 8)
                    self._send_short_msg(note_off)

                # Reset pitch bend to center on strike
                self._set_channel_pitch_bend(ch, 0)

                note_on = (0x90 | ch) | ((p & 0x7F) << 8) | ((velocity & 0x7F) << 16)
                self._send_short_msg(note_on)
                self._active_pitches[s_num] = p

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
        """Performs a smooth mechanical pull glide on an individual string channel
        without choking or re-striking the note.
        """
        if not self._opened:
            return

        ch = (string_num - 1) % 10
        # +/- 2 semitones maps to +/- 8191 bend units
        target_bend = int(max(-8191, min(8191, (semitone_delta / 2.0) * 8191)))

        def _glide_worker():
            steps = 16
            sleep_step = max(0.003, duration_sec / steps)
            start_bend = self._current_bends.get(ch, 0)

            for i in range(1, steps + 1):
                fraction = i / steps
                # Pedal steel mechanical ease curve
                curve = 0.5 - 0.5 * math.cos(fraction * math.pi)
                cur_bend = int(start_bend + (target_bend - start_bend) * curve)
                self._set_channel_pitch_bend(ch, cur_bend)
                time.sleep(sleep_step)

            self._set_channel_pitch_bend(ch, target_bend)

        threading.Thread(target=_glide_worker, daemon=True).start()

    def play_scale_sequence(self, pitches: List[int], delay: float = 0.38, velocity: int = 95):
        if not self._opened or not pitches:
            return

        valid_pitches = [int(p) for p in pitches if p > 0]
        if not valid_pitches:
            return

        def _worker():
            for p in valid_pitches:
                note_on = 0x90 | ((p & 0x7F) << 8) | ((velocity & 0x7F) << 16)
                self._send_short_msg(note_on)
                time.sleep(delay)

        threading.Thread(target=_worker, daemon=True).start()

    def set_compensated_temperament(self, enabled: bool):
        self.use_compensated_temperament = enabled

    def close(self):
        if self._opened and self._hmidi and self._hmidi.value:
            try:
                self._send_short_msg(0x000040B0)
                winmm.midiOutReset(self._hmidi)
                winmm.midiOutClose(self._hmidi)
            except Exception:
                pass
            self._opened = False
            self._hmidi = None