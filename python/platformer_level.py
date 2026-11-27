"""Shared collision/visual scene data; no model files or graphics required."""
from platformer_controller import StaticBox
from platformer_hazards import MovingHazard

SPAWN = (0, 0, 3)
BOXES = (
    StaticBox("Start floor", (-7, -1, -4), (7, 0, 7), "#608c54"),
    StaticBox("1", (-1.4, 0.6, -7), (1.4, 1, -4.8), "#ceae65"),
    StaticBox("2", (0.7, 1.5, -10.8), (3.5, 1.9, -8), "#c89352"),
    StaticBox("3", (-1.3, 2.3, -14.7), (1.5, 2.7, -11.9), "#bca36c"),
    StaticBox("4", (-4.3, 3.2, -18.3), (-1.5, 3.6, -15.7), "#ceae65"),
    StaticBox("Finish", (-6, 3.2, -23.5), (-0.5, 4.2, -19.3), "#79ac72"),
    StaticBox("Side wall", (4, 0, -1), (4.5, 3, 2), "#bb7569"),
    StaticBox("Head test roof", (-5, 2, -1), (-2.5, 2.45, 2), "#799bb3"),
)

# Damage volumes, not rideable platforms. Their paths never cover the spawn.
HAZARDS = (
    MovingHazard("Floor sweeper", (-3, 0.65, -2.4), (3, 0.65, -2.4),
                 (0.85, 1.3, 0.7), period=4.0),
    MovingHazard("Platform sweeper", (-0.3, 2.4, -9.4), (4.5, 2.4, -9.4),
                 (0.7, 1.0, 0.7), period=3.2),
    MovingHazard("High sweeper", (-5, 4.1, -17), (-0.8, 4.1, -17),
                 (0.7, 1.0, 0.7), period=3.6, phase=0.8),
)
