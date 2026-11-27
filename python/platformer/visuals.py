"""Replaceable scene art; collision geometry remains owned by StageWorld."""
import math

import numpy as np

from camera import rotate_y
from scene import srgb_hex_to_linear
from .inventory import CATALOG


class PlayerVisual:
    def __init__(self, resources, settings):
        self.resources = resources
        self.height = settings.height
        self.body = resources.instance("character", (0.64, self.height, 0.64), "#ead59a")
        self.face = resources.instance("face", (0.36, 0.13, 0.025), "#2b3d3c")
        self.hat = resources.instance("hat", (0.83, 0.16, 0.83), "#ffffff")
        self.hat_tops = [resources.instance("hat_tip", (0.18, 0.28, 0.18), "#ffffff") for _ in range(3)]
        self.wings = [resources.instance("back", (0.43, 0.75, 0.14), "#ffffff") for _ in range(2)]
        self.heading = 0.0

    def sync(self, player, dt, profile):
        speed = np.linalg.norm(player.velocity[[0, 2]])
        if speed > 0.1:
            self.heading = math.atan2(player.velocity[0], player.velocity[2])
        self.body.pos[:] = player.pos + (0, self.height / 2, 0)
        self.body.heading = self.heading
        equipped = profile["equipped"]
        color = CATALOG[equipped["color"]].color if "color" in equipped else "#ffffff"
        self.body.tint = np.array([*srgb_hex_to_linear(color), 1])
        model_animation = self.body.animator
        if model_animation is not None:
            clip = "jump" if not player.grounded else "walk" if speed > 0.1 else "idle"
            if not model_animation.has(clip):
                clip = "idle"
            model_animation.play(clip)
            model_animation.update(dt)
        rotation = rotate_y(self.heading)[:3, :3]
        self.face.pos[:] = player.pos + rotation @ np.array((0, self.height * 0.78, 0.335))
        self.face.heading = self.heading
        drawn = [self.body]
        if self.resources.models.get("character") is None:
            drawn.append(self.face)
        if "hat" in equipped:
            item = CATALOG[equipped["hat"]]
            tint = np.array([*srgb_hex_to_linear(item.color), 1])
            self.hat.pos[:] = player.pos + (0, self.height + 0.08, 0)
            self.hat.heading = self.heading
            self.hat.tint = tint
            drawn.append(self.hat)
            count = 3 if item.shape == "crown" else 1
            for i, tip in enumerate(self.hat_tops[:count]):
                tip.pos[:] = player.pos + rotation @ np.array(((i - (count - 1) / 2) * 0.28,
                                                               self.height + 0.28, 0))
                tip.tint = tint
                drawn.append(tip)
        if "back" in equipped:
            tint = np.array([*srgb_hex_to_linear(CATALOG[equipped["back"]].color), 1])
            for i, wing in enumerate(self.wings):
                wing.pos[:] = player.pos + rotation @ np.array(((-1 if i == 0 else 1) * 0.43,
                                                                self.height * 0.6, -0.4))
                wing.heading = self.heading
                wing.tint = tint
                drawn.append(wing)
        return drawn


class StageVisual:
    def __init__(self, resources, world):
        self.resources = resources
        self.world = world
        stage = world.stage
        self.static = []
        for box in stage.boxes:
            lo, hi = np.array(box.lo), np.array(box.hi)
            self.static.append(resources.instance("platform", hi - lo, box.color, (lo + hi) / 2))
        self.movers = [resources.instance("obstacle", h.size, h.color) for h in stage.hazards]
        self.monkeys, self.warning_art = [], []
        for monkey in stage.monkeys:
            pos = np.array(monkey.pos)
            self.static.append(resources.instance("perch", (1.3, 0.3, 1.3), "#75634e", pos - (0, 0.9, 0)))
            self.monkeys.append(resources.instance("monkey", (0.8, 1, 0.7), "#956a45", pos - (0, 0.2, 0)))
            for side in (-1, 1):
                self.static.append(resources.instance("ear", (0.26, 0.3, 0.22), "#c19970",
                                                      pos + (side * 0.48, 0.05, 0)))
            self.static.append(resources.instance("monkey_face", (0.52, 0.35, 0.05), "#e5c38e", pos + (0, 0, 0.37)))
            self.warning_art.append(resources.instance("warning", (0.2, 0.55, 0.2), "#ffd650", pos + (0, 0.95, 0)))
        for spike in stage.spikes:
            lo, hi = np.array(spike.lo), np.array(spike.hi)
            self.static.append(resources.instance("spike", hi - lo, spike.color, (lo + hi) / 2))
            # Several pointed-looking teeth distinguish the optional boost tile.
            for x in np.linspace(lo[0] + 0.05, hi[0] - 0.05, 3):
                self.static.append(resources.instance("spike_tip", (0.1, 0.25, (hi[2] - lo[2]) * 0.6),
                                                      "#f7c1ac", (x, hi[1], (hi[2] + lo[2]) / 2)))
        for rope in stage.ropes:
            self.static.append(resources.instance("rope", (0.09, rope.top - rope.bottom + 1.4, 0.09),
                                                  "#e2c07e", (rope.x, (rope.top + rope.bottom + 1.4) / 2, rope.z)))
        goal = stage.goal
        cx, cz = (goal.lo[0] + goal.hi[0]) / 2, (goal.lo[2] + goal.hi[2]) / 2
        for side in (-1, 1):
            self.static.append(resources.instance("goal", (0.2, 2.4, 0.2), "#ffdb74",
                                                  (cx + side * 1, goal.lo[1] + 1.2, cz)))
        self.static.append(resources.instance("goal", (2.2, 0.25, 0.25), "#ffdb74", (cx, goal.lo[1] + 2.4, cz)))
        # Decorative trees outside the route, so they cannot obscure landing spots.
        for i in range(12):
            x = (-1 if i % 2 else 1) * (8 + (i % 3))
            z = 4 - i * 2.7
            y = max(-1, -z * 0.12)
            self.static.append(resources.instance("tree", (2.4, 3.5, 2.4), "#3b7659", (x, y + 3, z)))
            self.static.append(resources.instance("trunk", (0.4, 2.2, 0.4), "#805e44", (x, y + 0.8, z)))
        self.bananas = [resources.instance("banana", (0.42, 0.16, 0.2), "#ffdb58")
                        for _ in range(world.settings.projectile_limit)]
        self.player = PlayerVisual(resources, world.player.settings)

    def sync(self, dt, profile):
        world = self.world
        drawn = list(self.static) + self.monkeys
        for hazard, instance in zip(world.stage.hazards, self.movers):
            instance.pos[:] = hazard.position(world.player.simulation_time)
            drawn.append(instance)
        for warning, instance in zip(world.warnings, self.warning_art):
            if warning:
                drawn.append(instance)
        for banana, instance in zip(world.projectiles, self.bananas):
            instance.pos[:] = banana.pos
            instance.heading = world.time * 10
            drawn.append(instance)
        drawn += self.player.sync(world.player, dt, profile)
        return drawn
