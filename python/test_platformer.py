"""Headless behavioral tests: python -m unittest -v test_platformer."""
import unittest

import numpy as np

from platformer_controller import MovementSettings, PlatformerController, StaticBox
from platformer_level import BOXES


FLOOR = StaticBox("floor", (-20, -1, -20), (20, 0, 20))


class MovementTests(unittest.TestCase):
    def player(self, boxes=(FLOOR,), spawn=(0, 0, 0), **settings):
        return PlatformerController(boxes, spawn, MovementSettings(**settings))

    def test_diagonal_and_cardinal_speed_match(self):
        a, b = self.player(), self.player()
        a.advance(1, (1, 0))
        b.advance(1, (1, 1))
        self.assertAlmostEqual(np.linalg.norm(a.pos[[0, 2]]), 4.5)
        self.assertAlmostEqual(np.linalg.norm(a.pos[[0, 2]]), np.linalg.norm(b.pos[[0, 2]]))

    def test_jump_height_and_apex_time(self):
        for height, apex in ((2.2, 0.5), (3, 0.75)):
            p = self.player(jump_height=height, time_to_apex=apex)
            p.set_jump_held(True)
            p.advance(apex)
            self.assertAlmostEqual(p.pos[1], height, places=8)
            self.assertAlmostEqual(p.velocity[1], 0, places=8)

    def test_hold_does_not_repeat_and_release_rearms(self):
        p = self.player()
        p.set_jump_held(True)
        for _ in range(240):
            p.set_jump_held(True)
            p.advance(1 / 120)
        self.assertTrue(p.grounded)
        self.assertEqual(p.pos[1], 0)
        self.assertEqual(p.velocity[1], 0)
        p.set_jump_held(False)
        p.set_jump_held(True)
        p.advance(1 / 120)
        self.assertGreater(p.velocity[1], 0)

    def test_air_press_neither_double_jumps_nor_buffers_landing(self):
        p = self.player()
        p.set_jump_held(True)
        p.advance(0.25)
        before = p.velocity[1]
        p.set_jump_held(False)
        p.set_jump_held(True)
        p.advance(1 / 120)
        self.assertLess(p.velocity[1], before)
        p.advance(2)
        self.assertTrue(p.grounded)
        self.assertEqual(p.pos[1], 0)

    def test_press_survives_render_frame_without_physics_tick(self):
        p = self.player()
        p.set_jump_held(True)
        p.advance(0.001)
        p.set_jump_held(False)
        p.advance(0.01)
        self.assertGreater(p.velocity[1], 0)

    def test_air_control_can_be_disabled_or_enabled(self):
        for control in (0, 0.65, 1):
            p = self.player(air_control=control)
            p.set_jump_held(True)
            p.advance(0.25, (1, 0))
            before = p.pos[0]
            p.advance(0.3, (-1, 0))
            if control == 0:
                self.assertGreater(p.pos[0], before)
            else:
                self.assertLess(p.velocity[0], 0)

    def test_lands_exactly_on_platform(self):
        platform = StaticBox("platform", (-2, 0.7, -2), (2, 1, 2))
        p = self.player((FLOOR, platform), (0, 5, 0))
        p.advance(2)
        self.assertEqual(p.pos[1], 1)
        self.assertEqual(p.velocity[1], 0)
        self.assertTrue(p.grounded)

    def test_walk_off_falls_without_sticky_ground(self):
        p = self.player((StaticBox("ledge", (-1, -1, -1), (1, 0, 1)),))
        p.advance(0.4, (1, 0))
        self.assertGreater(p.pos[0], 1.32)
        self.assertLess(p.pos[1], 0)
        self.assertFalse(p.grounded)
        self.assertLess(p.velocity[1], 0)

    def test_side_collision_cannot_step_up_or_pass(self):
        wall = StaticBox("wall", (1, 0, -2), (1.05, 3, 2))
        p = self.player((FLOOR, wall))
        p.advance(1, (1, 0))
        self.assertAlmostEqual(p.pos[0], 0.68)
        self.assertEqual(p.pos[1], 0)
        p.set_jump_held(True)
        p.advance(0.2, (1, 0))
        self.assertAlmostEqual(p.pos[0], 0.68)
        self.assertFalse(p.grounded)
        self.assertLess(p.pos[1], wall.hi[1])

    def test_wall_sliding_preserves_tangential_motion(self):
        wall = StaticBox("wall", (1, 0, -10), (1.1, 4, 10))
        p = self.player((FLOOR, wall))
        p.advance(1, (1, 1))
        self.assertAlmostEqual(p.pos[0], 0.68)
        self.assertGreater(p.pos[2], 3)

    def test_head_hit_stops_ascent_then_falls(self):
        roof = StaticBox("roof", (-2, 2, -2), (2, 2.05, 2))
        p = self.player((FLOOR, roof))
        p.set_jump_held(True)
        for _ in range(60):
            p.advance(1 / 120)
            self.assertLessEqual(p.pos[1] + p.settings.height, 2 + 1e-9)
            if p.velocity[1] == 0:
                break
        self.assertAlmostEqual(p.pos[1], 0.6)
        self.assertFalse(p.grounded)
        p.advance(1 / 120)
        self.assertLess(p.velocity[1], 0)
        self.assertLess(p.pos[1], 0.6)

    def test_slow_frames_match_fast_frames(self):
        a, b = self.player(), self.player()
        for p in (a, b):
            p.set_jump_held(True)
        for _ in range(240):
            a.advance(1 / 120, (1, 0))
        for dt in (0.37, 0.63, 0.8, 0.2):
            b.advance(dt, (1, 0))
        np.testing.assert_allclose(a.pos, b.pos, atol=1e-9)
        np.testing.assert_allclose(a.velocity, b.velocity, atol=1e-9)

    def test_sweeps_prevent_extreme_speed_thin_surface_tunnelling(self):
        thin = StaticBox("thin floor", (-5, -0.01, -5), (5, 0, 5))
        p = self.player((thin,), (0, 10, 0))
        p.velocity[1] = -10000
        p.advance(1 / 120)
        self.assertEqual(p.pos[1], 0)
        self.assertTrue(p.grounded)
        wall = StaticBox("thin wall", (1, 0, -1), (1.001, 3, 1))
        p = self.player((FLOOR, wall), move_speed=10000)
        p.advance(1 / 120, (1, 0))
        self.assertAlmostEqual(p.pos[0], 0.68)

    def test_respawn_clears_velocity_ground_and_pending_input(self):
        p = self.player((), (0, 0, 0), fall_reset_y=-1)
        p.set_jump_held(True)
        p.advance(1, (1, 0))
        np.testing.assert_array_equal(p.pos, p.spawn)
        np.testing.assert_array_equal(p.velocity, np.zeros(3))
        self.assertFalse(p.grounded)
        self.assertFalse(p._jump_pending)
        self.assertEqual(p.respawn_count, 1)
        self.assertEqual(p._accumulator, 0)

    def test_held_space_does_not_jump_after_respawn(self):
        p = self.player()
        p.set_jump_held(True)
        p.respawn()
        p.set_jump_held(True)
        p.advance(1 / 120)
        self.assertTrue(p.grounded)
        self.assertEqual(p.velocity[1], 0)

    def test_test_scene_route_is_reachable_at_default_settings(self):
        # Walk to the north edge; each following centre can be reached in one
        # jump. Control is released once centred above the destination.
        start = np.array((0., 0., -3.5))
        for target in BOXES[1:6]:
            p = self.player(BOXES, tuple(start))
            destination = (np.array(target.lo) + np.array(target.hi)) / 2
            p.set_jump_held(True)
            for _ in range(240):
                delta = destination[[0, 2]] - p.pos[[0, 2]]
                # Proportional braking avoids overshooting the destination.
                p.advance(1 / 120, delta * 3 / p.settings.move_speed)
                if p.grounded:
                    break
            self.assertTrue(p.grounded, target.name)
            self.assertAlmostEqual(p.pos[1], target.hi[1], msg=target.name)
            start = p.pos.copy()


if __name__ == "__main__":
    unittest.main()
