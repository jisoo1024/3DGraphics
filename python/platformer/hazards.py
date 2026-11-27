"""Moving damage volumes, independent of OpenGL and the player's visual model."""
from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class MovingHazard:
    name: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    size: tuple[float, float, float]
    period: float = 4.0  # seconds for a full round trip
    phase: float = 0.0  # seconds into the cycle at scene start
    color: str = "#dc4268"

    def __post_init__(self):
        if not math.isfinite(self.period) or self.period <= 0:
            raise ValueError("Hazard period must be finite and positive")
        if any(not math.isfinite(x) or x <= 0 for x in self.size):
            raise ValueError("Hazard dimensions must be finite and positive")

    def position(self, time):
        cycle = ((time + self.phase) % self.period) / self.period
        fraction = 1 - abs(2 * cycle - 1)
        return np.asarray(self.start) + (np.asarray(self.end) - self.start) * fraction

    def bounds(self, time):
        center = self.position(time)
        half = np.asarray(self.size) / 2
        return center - half, center + half

    def hits(self, before, after, player_size, start_time, end_time):
        """Sweep in relative space; split at turnarounds to retain the full path.

        before/after are the player's feet positions. Minkowski expansion turns
        the two moving AABBs into a segment-versus-box test, including a hazard
        that crosses the entire player between two physics ticks.
        """
        half_period = self.period / 2
        first = math.floor((start_time + self.phase) / half_period) + 1
        cuts = [start_time]
        turn = first * half_period - self.phase
        while turn < end_time:
            cuts.append(turn)
            turn += half_period
        cuts.append(end_time)
        before, after = np.asarray(before), np.asarray(after)
        size = np.asarray(player_size)
        offset = np.array((0, size[1] / 2, 0))
        extent = (np.asarray(self.size) + size) / 2
        duration = end_time - start_time
        for t0, t1 in zip(cuts, cuts[1:]):
            a = 0 if duration == 0 else (t0 - start_time) / duration
            b = 0 if duration == 0 else (t1 - start_time) / duration
            p0 = before + (after - before) * a + offset - self.position(t0)
            p1 = before + (after - before) * b + offset - self.position(t1)
            if segment_box(p0, p1, extent):
                return True
        return False


def segment_box(start, end, extent):
    enter, leave = 0.0, 1.0
    for origin, delta, half in zip(start, end - start, extent):
        if abs(delta) < 1e-12:
            if abs(origin) > half:
                return False
        else:
            a, b = (-half - origin) / delta, (half - origin) / delta
            enter, leave = max(enter, min(a, b)), min(leave, max(a, b))
            if enter > leave:
                return False
    return True
