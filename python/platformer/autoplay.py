"""Deterministic input pilot for integration verification (no teleporting)."""
import numpy as np


class CoursePilot:
    def __init__(self):
        self.world = None
        self.index = 0
        self.jumping = False

    def controls(self, world):
        if world is not self.world:
            self.world = world
            self.index = 0
            self.jumping = False
        player = world.player
        route = world.stage.route
        if self.index == 0:
            target = np.array(route[0])
            delta = target[[0, 2]] - player.pos[[0, 2]]
            if np.linalg.norm(delta) < 0.08 and player.grounded:
                self.index = 1
        if 0 < self.index < len(route):
            target = np.array(route[self.index])
            if not self.jumping and player.grounded and player.knockback_left <= player.EPS:
                player.set_jump_held(False)
                player.set_jump_held(True)
                self.jumping = True
            elif self.jumping and player.grounded:
                player.set_jump_held(False)
                self.index += 1
                self.jumping = False
        elif self.index >= len(route):
            target = (np.array(world.stage.goal.lo) + world.stage.goal.hi) / 2
        else:
            target = np.array(route[0])
        return (target[[0, 2]] - player.pos[[0, 2]]) * 3 / player.settings.move_speed
