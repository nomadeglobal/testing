"""Logique pure de surveillance (sans OBS ni réseau), facile à tester."""
from __future__ import annotations

import math
from dataclasses import dataclass, field


def mul_to_db(mul: float) -> float:
    """Amplitude linéaire (0..1) -> dBFS. 0 donne -inf."""
    return 20 * math.log10(mul) if mul > 0 else float("-inf")


@dataclass
class AudioWatch:
    floor_db: float
    silence_alert_s: float
    stop_after_silence_s: float  # 0 = désactivé
    last_sound_t: float | None = None
    heard_sound: bool = False
    started_t: float | None = None
    alerted: bool = field(default=False)

    def feed(self, peak_db: float, now: float) -> None:
        if self.started_t is None:
            self.started_t = now
        if peak_db > self.floor_db:
            self.last_sound_t = now
            self.heard_sound = True
            self.alerted = False

    def silent_for(self, now: float) -> float:
        ref = self.last_sound_t if self.last_sound_t is not None else self.started_t
        return 0.0 if ref is None else now - ref

    def should_alert(self, now: float) -> bool:
        if self.alerted or self.silent_for(now) < self.silence_alert_s:
            return False
        self.alerted = True
        return True

    def should_stop(self, now: float) -> bool:
        return (
            self.stop_after_silence_s > 0
            and self.heard_sound
            and self.silent_for(now) >= self.stop_after_silence_s
        )


@dataclass
class FileWatch:
    stall_s: float
    last_size: int = -1
    last_growth_t: float | None = None
    alerted: bool = False

    def feed(self, size: int, now: float) -> None:
        if self.last_growth_t is None or size > self.last_size:
            self.last_growth_t = now
            self.alerted = False
        self.last_size = size

    def should_alert(self, now: float) -> bool:
        if self.alerted or self.last_growth_t is None:
            return False
        if now - self.last_growth_t >= self.stall_s:
            self.alerted = True
            return True
        return False
