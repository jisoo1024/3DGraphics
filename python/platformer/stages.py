"""Two editable courses; all geometry and enemy configuration lives here."""
from dataclasses import dataclass

from .controller import StaticBox
from .level import BOXES, HAZARDS, SPAWN


@dataclass(frozen=True)
class Monkey:
    pos: tuple
    interval: float = 3.5
    speed: float = 5.0
    range: float = 12
    direction: tuple | None = None  # None aims at player once at release
    phase: float = 0


@dataclass(frozen=True)
class Rope:
    x: float
    z: float
    bottom: float
    top: float


@dataclass(frozen=True)
class Stage:
    name: str
    spawn: tuple
    boxes: tuple
    goal: StaticBox
    route: tuple  # safe takeoff waypoint followed by landing targets
    hazards: tuple = ()
    monkeys: tuple = ()
    spikes: tuple = ()
    ropes: tuple = ()


SECOND_BOXES = (
    StaticBox("시작", (-4, -1, -2.8), (4, 0, 5), "#557f70"),
    StaticBox("1", (-1.1, 0.65, -5.8), (1.1, 1, -3.6), "#a2a877"),
    StaticBox("2", (0.8, 1.65, -9.2), (3, 2, -7), "#aaa16d"),
    StaticBox("3", (-0.9, 2.65, -12.7), (1.3, 3, -10.5), "#a2a877"),
    StaticBox("4", (-3, 3.65, -16), (-0.8, 4, -13.8), "#aaa16d"),
    StaticBox("5", (-1, 4.65, -19.4), (1.2, 5, -17.2), "#a2a877"),
    StaticBox("도착", (0.7, 5.65, -24), (4.3, 6, -20.6), "#80b997"),
    # Optional spike/rope shortcut at the side of the primary jump route.
    StaticBox("지름길 쉼터", (3.9, 1.2, -5.6), (6.1, 1.6, -3.4), "#ad9475"),
)

STAGES = (
    Stage("1 · 숲의 입구", SPAWN, BOXES,
          StaticBox("도착", (-4.7, 4.2, -23.2), (-1.3, 6.2, -21), "#f5d46d"),
          ((0, 0, -3.5),) + tuple(((b.lo[0] + b.hi[0]) / 2, b.hi[1],
                                   (b.lo[2] + b.hi[2]) / 2) for b in BOXES[1:6]),
          hazards=HAZARDS[:1],
          monkeys=(Monkey((3.6, 2.6, -6.5), interval=4.2, speed=4.2),
                   Monkey((-3.4, 4.4, -14), interval=4, speed=4.5, phase=1))),
    Stage("2 · 깊은 숲", (0, 0, 3), SECOND_BOXES,
          StaticBox("도착", (1.2, 6, -23.8), (3.8, 8, -22), "#f5d46d"),
          ((0, 0, -2.3),) + tuple(((b.lo[0] + b.hi[0]) / 2, b.hi[1],
                                   (b.lo[2] + b.hi[2]) / 2) for b in SECOND_BOXES[1:7]),
          monkeys=(Monkey((-3, 3, -7.7), interval=3.5, speed=4.8),
                   Monkey((3.5, 5.5, -15), interval=3.6, speed=5, phase=1.2)),
          spikes=(StaticBox("가시", (2.6, 0, -1), (3.5, 0.35, 0.3), "#df7a83"),
                  StaticBox("가시", (2.3, 2, -8.8), (2.85, 2.3, -8.2), "#df7a83")),
          ropes=(Rope(3.55, -3.0, 0.1, 2.6), Rope(-1.05, -12.6, 2.6, 5.4))),
)
