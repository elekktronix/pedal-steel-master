"""Generated WAV woodblock "chirp" for metronome clicks (flashcards, permutation trainer).

Moved out of the retired voice leader window (E-32). It plays through the sound card, not the MIDI
scheduler, so it can drift against MIDI notes; timing-critical playback uses
`MidiAudioEngine.play_click` instead.
"""

import math
import struct
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect


class MetronomeChirp:
    """Generates and plays crisp, authentic electronic woodblock clicks/chirps."""
    def __init__(self):
        self.sound_hi: Optional[QSoundEffect] = None
        self.sound_lo: Optional[QSoundEffect] = None
        self._init_sounds()

    def _init_sounds(self):
        temp_dir = Path(tempfile.gettempdir())
        path_hi = temp_dir / "psg_metronome_chirp_hi.wav"
        path_lo = temp_dir / "psg_metronome_chirp_lo.wav"

        if not path_hi.exists():
            self._write_chirp_wav(str(path_hi), base_freq=2600.0, duration_ms=18.0)
        if not path_lo.exists():
            self._write_chirp_wav(str(path_lo), base_freq=1500.0, duration_ms=14.0)

        self.sound_hi = QSoundEffect()
        self.sound_hi.setSource(QUrl.fromLocalFile(str(path_hi)))
        self.sound_hi.setVolume(0.95)

        self.sound_lo = QSoundEffect()
        self.sound_lo.setSource(QUrl.fromLocalFile(str(path_lo)))
        self.sound_lo.setVolume(0.75)

    def _write_chirp_wav(self, filepath: str, base_freq: float, duration_ms: float):
        sample_rate = 44100
        num_samples = int(sample_rate * (duration_ms / 1000.0))
        raw_data = bytearray()

        for i in range(num_samples):
            t = i / sample_rate
            decay = math.exp(-i / (num_samples * 0.22))
            sweep = base_freq * (1.0 + 0.9 * math.exp(-i / (num_samples * 0.12)))
            val = math.sin(2.0 * math.pi * sweep * t) * decay
            sample_val = int(max(-32767, min(32767, val * 30000)))
            raw_data.extend(struct.pack("<h", sample_val))

        data_size = len(raw_data)
        with open(filepath, "wb") as f:
            f.write(b"RIFF")
            f.write(struct.pack("<I", 36 + data_size))
            f.write(b"WAVE")
            f.write(b"fmt ")
            f.write(struct.pack("<I", 16))
            f.write(struct.pack("<H", 1))
            f.write(struct.pack("<H", 1))
            f.write(struct.pack("<I", sample_rate))
            f.write(struct.pack("<I", sample_rate * 2))
            f.write(struct.pack("<H", 2))
            f.write(struct.pack("<H", 16))
            f.write(b"data")
            f.write(struct.pack("<I", data_size))
            f.write(raw_data)

    def play(self, is_downbeat: bool):
        if is_downbeat and self.sound_hi:
            self.sound_hi.play()
        elif not is_downbeat and self.sound_lo:
            self.sound_lo.play()
