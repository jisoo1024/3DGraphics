"""Renderer-independent, Y-up kinematic AABB platform controller.

Positions refer to the centre of the feet. Static boxes must not overlap the
spawn. Fixed steps plus swept axis clipping prevent tunnelling through boxes;
there is deliberately no step-up, slope handling or moving-platform support.
"""
from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class MovementSettings:
    move_speed: float = 4.5
    jump_height: float = 2.2
    time_to_apex: float = 0.5
    air_control: float = 0.65  # 0 retains takeoff velocity; 1 gives ground response
    fall_reset_y: float = -12.0
    half_width: float = 0.32
    height: float = 1.4
    fixed_dt: float = 1 / 120
    hit_invulnerability: float = 1.0
    knockback_speed: float = 3.5  # m/s, horizontal impulse away from the hazard
    knockback_duration: float = 0.18  # seconds, about 0.63m on unobstructed ground

    def __post_init__(self):
        if min(self.jump_height, self.time_to_apex, self.half_width,
               self.height, self.fixed_dt) <= 0 or self.move_speed < 0:
            raise ValueError("Dimensions, jump and fixed_dt must be positive; speed nonnegative")
        if not 0 <= self.air_control <= 1:
            raise ValueError("air_control must be between 0 and 1")
        if self.hit_invulnerability < 0:
            raise ValueError("hit_invulnerability must be nonnegative")
        if any(not math.isfinite(x) or x < 0 for x in
               (self.knockback_speed, self.knockback_duration)):
            raise ValueError("Knockback speed and duration must be finite and nonnegative")

    @property
    def gravity(self):
        return 2 * self.jump_height / self.time_to_apex ** 2

    @property
    def jump_speed(self):
        return 2 * self.jump_height / self.time_to_apex


@dataclass(frozen=True)
class StaticBox:
    name: str
    lo: tuple[float, float, float]
    hi: tuple[float, float, float]
    color: str = "#7cb85a"


class PlatformerController:
    EPS = 1e-9

    def __init__(self, boxes, spawn=(0, 0, 3), settings=None, hazards=()):
        self.settings = settings or MovementSettings()
        self.boxes = tuple(boxes)
        self.spawn = np.array(spawn, dtype=float)
        self.pos = self.spawn.copy()
        self.velocity = np.zeros(3)
        self.grounded = False
        self._accumulator = 0.0
        self._jump_down = False
        self._jump_pending = False
        self.respawn_count = 0
        self.hazards = tuple(hazards)
        self.simulation_time = 0.0
        self.hit_count = 0
        self.invulnerability_left = 0.0
        self.last_hit = None
        self.knockback_left = 0.0
        self.rope = None
        self.climb_input = 0.0
        self.events = []
        self.grounded = self._supported()

    def bounds(self):
        s = self.settings
        return (self.pos + (-s.half_width, 0, -s.half_width),
                self.pos + (s.half_width, s.height, s.half_width))

    def _overlaps(self, lo, hi, box, axes):
        return all(hi[a] > box.lo[a] + self.EPS and
                   lo[a] < box.hi[a] - self.EPS for a in axes)

    def _supported(self):
        lo, hi = self.bounds()
        return any(abs(lo[1] - b.hi[1]) <= self.EPS and
                   self._overlaps(lo, hi, b, (0, 2)) for b in self.boxes)

    def set_jump_held(self, held):
        """Sample button transitions, including frames with no physics step.

        Airborne presses are discarded, never buffered until landing. A held
        button stays latched across respawn until released.
        """
        if held and not self._jump_down and (self.grounded or self.rope is not None):
            self._jump_pending = True
        self._jump_down = bool(held)

    def respawn(self):
        self.pos[:] = self.spawn
        self.velocity[:] = 0
        self.grounded = False
        self._jump_pending = False
        self._accumulator = 0.0
        self.knockback_left = 0.0
        self.invulnerability_left = 0.0
        self.last_hit = None
        self.rope = None
        self.climb_input = 0.0
        self.events.append("respawn")
        self.respawn_count += 1

    @property
    def state(self):
        if self.rope is not None:
            return "rope"
        if self.knockback_left > self.EPS:
            return "stunned"
        return "grounded" if self.grounded else "airborne"

    def damage(self, origin, name="장애물", upward=0.0):
        if self.invulnerability_left > self.EPS:
            return False
        away = (self.pos - np.asarray(origin))[[0, 2]]
        if np.linalg.norm(away) <= self.EPS:
            away = -self.velocity[[0, 2]]
        if np.linalg.norm(away) <= self.EPS:
            away = np.array((0.0, 1.0))
        self._apply_hit(away, name, upward)
        return True

    def _apply_hit(self, away, name, upward=0.0):
        s = self.settings
        self.hit_count += 1
        self.last_hit = name
        self.invulnerability_left = s.hit_invulnerability
        self.knockback_left = s.knockback_duration
        self.rope = None
        if s.knockback_duration > 0:
            self.velocity[[0, 2]] = away / np.linalg.norm(away) * s.knockback_speed
        if upward > 0:
            self.velocity[1] = upward
            self.grounded = False
        self._jump_pending = False
        self.events.append("hit")

    def _take_hit(self, hazard, before, start_time):
        # Use the side from which contact began, even when a fast obstacle has
        # already crossed to the other side by the end of this physics tick.
        away = (before - hazard.position(start_time))[[0, 2]]
        if np.linalg.norm(away) <= self.EPS:
            away = (hazard.position(self.simulation_time)
                    - hazard.position(start_time))[[0, 2]]
        if np.linalg.norm(away) <= self.EPS:
            away = -self.velocity[[0, 2]]
        if np.linalg.norm(away) <= self.EPS:
            away = np.array((0.0, 1.0))
        self._apply_hit(away, hazard.name)
        # Keep position, vertical velocity and support: being hit never teleports
        # or grants another jump. The next steps resolve knockback against walls.

    def _move_axis(self, axis, distance):
        if distance == 0:
            return False
        lo, hi = self.bounds()
        other = tuple(a for a in range(3) if a != axis)
        allowed = distance
        hit = False
        for box in self.boxes:
            if not self._overlaps(lo, hi, box, other):
                continue
            if distance > 0 and hi[axis] <= box.lo[axis] + self.EPS:
                gap = max(0.0, box.lo[axis] - hi[axis])
                if gap <= allowed:
                    allowed, hit = gap, True
            elif distance < 0 and lo[axis] >= box.hi[axis] - self.EPS:
                gap = min(0.0, box.hi[axis] - lo[axis])
                if gap >= allowed:
                    allowed, hit = gap, True
        self.pos[axis] += allowed
        if hit:
            self.velocity[axis] = 0
        return hit

    def advance(self, dt, move=(0, 0)):
        """Consume elapsed seconds without dropping slow frames. move is (x,z)."""
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("dt must be finite and nonnegative")
        direction = np.array(move, dtype=float)
        length = float(np.linalg.norm(direction))
        if length > 1:
            direction /= length
        self._accumulator += dt
        step = self.settings.fixed_dt
        while self._accumulator + self.EPS >= step:
            self._accumulator = max(0, self._accumulator - step)
            before = self.pos.copy()
            start_time = self.simulation_time
            self._step(step, direction)
            self.simulation_time += step
            self.invulnerability_left = max(0, self.invulnerability_left - step)
            s = self.settings
            if self.invulnerability_left <= self.EPS:
                for hazard in self.hazards:
                    if hazard.hits(before, self.pos, (2 * s.half_width, s.height,
                                                     2 * s.half_width),
                                   start_time, self.simulation_time):
                        self._take_hit(hazard, before, start_time)
                        break
            if self.pos[1] < self.settings.fall_reset_y:
                self.respawn()
                break

    def _step(self, dt, direction):
        s = self.settings
        rope_jump = False
        if self.rope is not None:
            if self._jump_pending:
                self.rope = None
                self.velocity[1] = s.jump_speed
                self._jump_pending = False
                rope_jump = True
                self.events.append("jump")
            else:
                from .config import DEFAULTS
                delta = max(-1, min(1, self.climb_input)) * DEFAULTS.rope_speed * dt
                y = np.clip(self.pos[1] + delta, self.rope.bottom, self.rope.top)
                self._move_axis(1, y - self.pos[1])
                self.velocity[:] = 0
                self.grounded = False
                return
        was_grounded = self.grounded
        self.grounded = self.velocity[1] <= 0 and self._supported()
        knocked_back = self.knockback_left > self.EPS
        if knocked_back:
            # Briefly retain the hit impulse; normal input must not immediately
            # overwrite it, especially while grounded. Wall clipping still wins.
            self.knockback_left = max(0, self.knockback_left - dt)
        else:
            target = direction * s.move_speed
            blend = 1 if self.grounded else 1 - math.exp(-30 * s.air_control * dt)
            self.velocity[[0, 2]] += (target - self.velocity[[0, 2]]) * blend
        if self._jump_pending and self.grounded and not knocked_back:
            self.velocity[1] = s.jump_speed
            self.grounded = False
            self.events.append("jump")
        self._jump_pending = False

        self._move_axis(0, self.velocity[0] * dt)
        self._move_axis(2, self.velocity[2] * dt)
        # Exact constant-acceleration displacement gives the configured apex.
        dy = self.velocity[1] * dt - 0.5 * s.gravity * dt * dt
        self.velocity[1] -= s.gravity * dt
        hit = self._move_axis(1, dy)
        self.grounded = bool(hit and dy < 0)
        if self.grounded and not was_grounded and not rope_jump:
            self.events.append("land")
        # Side and ceiling hits never mark the character as grounded.
