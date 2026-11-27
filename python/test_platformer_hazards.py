"""Behavioral tests for damage sweeps and mouse-driven camera controls."""
import unittest
from unittest.mock import patch

import numpy as np
import pygame

from camera import FollowCamera
from platformer_controller import MovementSettings, PlatformerController, StaticBox
from platformer_hazards import MovingHazard
from platformer_input import MouseLook
from platformer_level import HAZARDS, SPAWN


FLOOR = StaticBox("floor", (-20, -1, -20), (20, 0, 20))


class HazardTests(unittest.TestCase):
    def test_patrol_endpoints_and_round_trip(self):
        h = MovingHazard("test", (-2, 1, 0), (2, 1, 0), (1, 1, 1), period=4)
        for t, expected in ((0, h.start), (1, (0, 1, 0)), (2, h.end), (4, h.start)):
            np.testing.assert_allclose(h.position(t), expected)

    def test_hazard_crossing_stationary_player_hits(self):
        h = MovingHazard("fast", (-3, 0.7, 0), (3, 0.7, 0), (0.2, 1, 0.2), period=0.02)
        p = PlatformerController((FLOOR,), spawn=(0, 0, 0), hazards=(h,))
        p.advance(1 / 120)
        self.assertEqual(p.hit_count, 1)
        self.assertEqual(p.last_hit, "fast")
        self.assertGreater(p.velocity[0], 0)
        np.testing.assert_array_equal(p.pos, p.spawn)
        self.assertEqual(p.respawn_count, 0)
        self.assertTrue(p.grounded)
        self.assertEqual(p.invulnerability_left, 1)

    def test_turnaround_path_detected_when_both_endpoints_miss(self):
        h = MovingHazard("turn", (-3, 0.7, 0), (3, 0.7, 0), (0.2, 1, 0.2), period=0.008)
        feet = np.zeros(3)
        self.assertTrue(h.hits(feet, feet, (0.64, 1.4, 0.64), 0, 0.008))

    def test_player_crossing_hazard_between_steps_hits(self):
        h = MovingHazard("still", (0, 0.7, 0), (0, 0.7, 0), (0.2, 1, 0.2))
        self.assertTrue(h.hits((-3, 0, 0), (3, 0, 0), (0.64, 1.4, 0.64), 0, 0.01))

    def test_jump_above_or_pass_beside_does_not_hit(self):
        h = MovingHazard("low", (-3, 0.5, 0), (3, 0.5, 0), (0.5, 1, 0.5), period=2)
        for feet in (np.array((0, 1.1, 0)), np.array((0, 0, 2))):
            self.assertFalse(h.hits(feet, feet, (0.64, 1.4, 0.64), 0, 1))

    def test_invulnerability_prevents_repeated_hits_then_expires(self):
        h = MovingHazard("still", (0, 0.7, 0), (0, 0.7, 0), (20, 1, 20))
        p = PlatformerController((FLOOR,), spawn=(0, 0, 0), hazards=(h, h))
        p.advance(1 / 120)
        self.assertEqual(p.hit_count, 1)
        p.set_jump_held(True)
        p.advance(0.5)
        self.assertEqual(p.hit_count, 1)
        self.assertTrue(p.grounded)
        self.assertEqual(p.velocity[1], 0)  # a press during knockback is not buffered
        p.advance(0.6)
        self.assertEqual(p.hit_count, 2)

    def test_slow_render_frame_does_not_skip_a_hit(self):
        h = MovingHazard("sweep", (-3, 0.7, 0), (3, 0.7, 0), (0.5, 1, 0.5), period=2)
        players = [PlatformerController((FLOOR,), spawn=(0, 0, 0), hazards=(h,)) for _ in range(2)]
        players[0].advance(0.5)
        for _ in range(60):
            players[1].advance(1 / 120)
        self.assertEqual(players[0].hit_count, 1)
        self.assertEqual(players[1].hit_count, 1)
        self.assertAlmostEqual(players[0].simulation_time, players[1].simulation_time)
        np.testing.assert_allclose(players[0].pos, players[1].pos, atol=1e-9)
        np.testing.assert_allclose(players[0].velocity, players[1].velocity, atol=1e-9)

    def test_spawn_outside_all_hazard_paths(self):
        for hazard in HAZARDS:
            self.assertFalse(hazard.hits(SPAWN, SPAWN, (0.64, 1.4, 0.64), 0, hazard.period))

    def test_knockback_stays_near_contact_and_control_returns(self):
        h = MovingHazard("side", (1.5, 0.7, 0), (1.5, 0.7, 0), (0.8, 1, 0.8))
        p = PlatformerController((FLOOR,), spawn=(-10, 0, 0), hazards=(h,))
        p.pos[:] = (2, 0, 0)
        p.advance(1 / 120)
        self.assertEqual(p.hit_count, 1)
        self.assertEqual(p.respawn_count, 0)
        self.assertEqual(p.pos[0], 2)  # hit applies velocity, no instant displacement
        p.advance(0.25, (-1, 0))
        self.assertGreater(p.pos[0], 2)
        self.assertLess(p.pos[0], 3)  # slight push, under one metre
        self.assertLess(p.velocity[0], 0)  # control has returned after 0.18s
        self.assertTrue(p.grounded)

    def test_knockback_cannot_pass_through_wall(self):
        h = MovingHazard("side", (1.5, 0.7, 0), (1.5, 0.7, 0), (0.8, 1, 0.8))
        wall = StaticBox("wall", (2.5, 0, -2), (2.55, 3, 2))
        p = PlatformerController((FLOOR, wall), spawn=(2, 0, 0), hazards=(h,))
        p.advance(0.3)
        self.assertAlmostEqual(p.pos[0], 2.18)
        self.assertEqual(p.velocity[0], 0)
        self.assertEqual(p.pos[1], 0)

    def test_airborne_hit_preserves_vertical_motion(self):
        h = MovingHazard("side", (-0.5, 1.7, 0), (-0.5, 1.7, 0), (0.8, 1, 0.8))
        p = PlatformerController((FLOOR,), spawn=(0, 0, 0), hazards=(h,))
        p.pos[1] = 1
        p.velocity[1] = -2
        p.advance(1 / 120)
        self.assertEqual(p.hit_count, 1)
        self.assertGreater(p.pos[1], 0.9)
        self.assertFalse(p.grounded)
        self.assertAlmostEqual(p.velocity[1], -2 - p.settings.gravity / 120)
        self.assertGreater(p.velocity[0], 0)

    def test_push_over_ledge_falls_and_only_then_respawns(self):
        ledge = StaticBox("ledge", (-1, -1, -1), (1, 0, 1))
        h = MovingHazard("side", (0.3, 0.7, 0), (0.3, 0.7, 0), (0.8, 1, 0.8))
        p = PlatformerController((ledge,), spawn=(0, 0, 0),
                                 settings=MovementSettings(fall_reset_y=-1), hazards=(h,))
        p.pos[0] = 0.8
        p.advance(0.25)
        self.assertEqual(p.respawn_count, 0)
        self.assertFalse(p.grounded)
        self.assertLess(p.pos[1], 0)
        p.advance(1)
        self.assertEqual(p.respawn_count, 1)
        self.assertEqual(p.knockback_left, 0)
        np.testing.assert_array_equal(p.velocity, np.zeros(3))
        np.testing.assert_array_equal(p.pos, p.spawn)


class MouseLookTests(unittest.TestCase):
    def setUp(self):
        for name in ("pygame.event.set_grab", "pygame.mouse.set_visible", "pygame.mouse.get_rel"):
            mock = patch(name)
            mock.start()
            self.addCleanup(mock.stop)
        self.camera = FollowCamera()
        self.look = MouseLook(self.camera)

    def test_mouse_motion_rotates_without_buttons(self):
        self.look.handle(pygame.event.Event(pygame.MOUSEMOTION, rel=(20, 10), buttons=(0, 0, 0)))
        self.assertAlmostEqual(self.camera.yaw, -0.1)
        self.assertAlmostEqual(self.camera.pitch, 0.4)

    def test_tab_releases_and_click_recaptures(self):
        self.look.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
        self.assertFalse(self.look.captured)
        self.look.handle(pygame.event.Event(pygame.MOUSEMOTION, rel=(100, 100)))
        self.assertEqual(self.camera.yaw, 0)
        self.look.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1))
        self.assertTrue(self.look.captured)

    def test_focus_loss_releases_mouse_until_explicit_recapture(self):
        self.look.handle(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.assertFalse(self.look.captured)
        self.assertFalse(self.look.focused)
        self.look.handle(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
        self.assertTrue(self.look.focused)
        self.assertFalse(self.look.captured)
        self.look.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
        self.assertTrue(self.look.captured)


if __name__ == "__main__":
    unittest.main()
