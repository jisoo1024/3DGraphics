"""Fixed-step stage simulation: monkeys, ballistic bananas, spikes and ropes."""
from dataclasses import dataclass
import math

import numpy as np

from .config import DEFAULTS
from .controller import PlatformerController


def sweep_fraction(start, end, lo, hi):
    """First segment/AABB contact, including starting inside; None on a miss."""
    enter, leave = 0.0, 1.0
    for p, d, low, high in zip(start, np.asarray(end) - start, lo, hi):
        if abs(d) < 1e-12:
            if p < low or p > high:
                return None
        else:
            a, b = (low - p) / d, (high - p) / d
            enter, leave = max(enter, min(a, b)), min(leave, max(a, b))
            if enter > leave:
                return None
    return enter


def overlap(a, b):
    return bool(np.all(np.asarray(a[1]) >= b[0]) and np.all(np.asarray(a[0]) <= b[1]))


@dataclass
class Banana:
    pos: np.ndarray
    velocity: np.ndarray
    age: float = 0
    radius: float = 0.18


class StageWorld:
    def __init__(self, stage, movement=None, settings=DEFAULTS):
        self.stage, self.settings = stage, settings
        self.player = PlatformerController(stage.boxes, stage.spawn, movement, stage.hazards)
        self.projectiles = []
        self.monkey_clocks = [m.phase for m in stage.monkeys]
        self.warnings = [False] * len(stage.monkeys)
        self.accumulator = 0.0
        self.time = 0.0
        self.events = []
        self.completed = False

    def dispose(self):
        self.projectiles.clear()
        self.monkey_clocks.clear()
        self.warnings.clear()
        self.events.clear()
        self.player.events.clear()
        self.player.rope = None

    def near_rope(self):
        p = self.player
        for rope in self.stage.ropes:
            if (np.hypot(p.pos[0] - rope.x, p.pos[2] - rope.z) <= self.settings.rope_reach
                    and rope.bottom - 0.2 <= p.pos[1] <= rope.top + 0.2):
                return rope
        return None

    def grab_rope(self):
        p = self.player
        rope = self.near_rope()
        if rope is None or p.knockback_left > p.EPS or p.rope is not None:
            return False
        # Sweep sideways into alignment so a nearby wall cannot be crossed.
        old = p.pos.copy()
        p._move_axis(0, rope.x - p.pos[0])
        p._move_axis(2, rope.z - p.pos[2])
        if np.hypot(p.pos[0] - rope.x, p.pos[2] - rope.z) > 0.01:
            p.pos[:] = old
            return False
        p.rope = rope
        p.velocity[:] = 0
        p.grounded = False
        p._jump_pending = False
        return True

    def update(self, dt, move=(0, 0), climb=0):
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("dt must be finite and nonnegative")
        self.accumulator += dt
        step = self.player.settings.fixed_dt
        while self.accumulator + 1e-9 >= step and not self.completed:
            self.accumulator = max(0, self.accumulator - step)
            self.fixed_update(step, move, climb)

    def fixed_update(self, dt, move, climb):
        p = self.player
        old = p.pos.copy()
        resets = p.respawn_count
        p.climb_input = climb
        p.advance(dt, move)
        self.time += dt
        if p.respawn_count != resets:
            old = p.pos.copy()  # respawn is not a damage sweep across the map
            self.projectiles.clear()
        self._monkeys(dt)
        self._bananas(dt, old)
        for spike in self.stage.spikes:
            size = np.array((p.settings.half_width, p.settings.height / 2, p.settings.half_width))
            center0 = old + (0, size[1], 0)
            center1 = p.pos + (0, size[1], 0)
            if sweep_fraction(center0, center1, np.array(spike.lo) - size,
                              np.array(spike.hi) + size) is not None:
                origin = (np.array(spike.lo) + spike.hi) / 2
                p.damage(origin, "가시", self.settings.spike_impulse)
        if p.grounded and overlap(p.bounds(), (self.stage.goal.lo, self.stage.goal.hi)):
            self.completed = True
        self.events.extend(p.events)
        p.events.clear()

    def _monkeys(self, dt):
        for i, monkey in enumerate(self.stage.monkeys):
            self.monkey_clocks[i] += dt
            clock = self.monkey_clocks[i]
            delta = self.player.pos + (0, 0.7, 0) - np.array(monkey.pos)
            in_range = np.linalg.norm(delta) <= monkey.range
            self.warnings[i] = in_range and clock >= monkey.interval - self.settings.warning_seconds
            if clock >= monkey.interval:
                self.monkey_clocks[i] %= monkey.interval
                if in_range and len(self.projectiles) < self.settings.projectile_limit:
                    if monkey.direction is not None:
                        direction = np.array(monkey.direction, float)
                        direction /= max(np.linalg.norm(direction), 1e-9)
                        velocity = direction * monkey.speed
                    else:
                        distance = np.linalg.norm(delta[[0, 2]])
                        flight = max(0.3, distance / monkey.speed)
                        velocity = delta / flight
                        velocity[1] += 0.5 * self.settings.projectile_gravity * flight
                    self.projectiles.append(Banana(np.array(monkey.pos, float), velocity))
                    self.events.append("throw")

    def _bananas(self, dt, player_before):
        p = self.player
        alive = []
        half = np.array((p.settings.half_width, p.settings.height / 2, p.settings.half_width))
        offset = np.array((0, half[1], 0))
        for banana in self.projectiles:
            before = banana.pos.copy()
            banana.age += dt
            banana.pos += banana.velocity * dt + np.array((0, -0.5 * self.settings.projectile_gravity * dt**2, 0))
            banana.velocity[1] -= self.settings.projectile_gravity * dt
            terrain_hit = 2.0
            for box in self.stage.boxes:
                fraction = sweep_fraction(before, banana.pos, np.array(box.lo) - banana.radius,
                                          np.array(box.hi) + banana.radius)
                if fraction is not None:
                    terrain_hit = min(terrain_hit, fraction)
            relative_start = before - (player_before + offset)
            relative_end = banana.pos - (p.pos + offset)
            player_hit = sweep_fraction(relative_start, relative_end, -half - banana.radius,
                                        half + banana.radius)
            if player_hit is not None and player_hit <= terrain_hit:
                origin = before + (banana.pos - before) * player_hit
                p.damage(origin, "바나나")
                continue
            if terrain_hit <= 1 or banana.age >= self.settings.projectile_lifetime:
                continue
            alive.append(banana)
        self.projectiles = alive
