"""Game-wide defaults. Movement tuning remains in controller.MovementSettings."""
from dataclasses import dataclass


@dataclass(frozen=True)
class GameSettings:
    base_reward: int = 100
    maximum_reward: int = 600
    bonus_seconds: float = 240
    bonus_per_second: float = 2
    projectile_gravity: float = 7
    projectile_lifetime: float = 5
    projectile_limit: int = 24
    warning_seconds: float = 0.65
    spike_impulse: float = 12
    rope_speed: float = 2.8
    rope_reach: float = 0.85


DEFAULTS = GameSettings()
DEFAULT_OPTIONS = {"bgm": 0.35, "sfx": 0.65, "sensitivity": 1.0, "shadows": True}
