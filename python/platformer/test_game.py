"""Headless integration tests for full game rules and stage lifecycle."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

from .camera import GameCamera
from .autoplay import CoursePilot
from .config import DEFAULTS
from .controller import PlatformerController, StaticBox
from .inventory import ITEMS, purchase, toggle_equip
from .progress import Progress, Screen, reward_for
from .save import SaveStore, defaults, validate
from .session import Session
from .resources import Resources
from .audio import Audio
from .stages import Monkey, Rope, STAGES, Stage
from .world import Banana, StageWorld


FLOOR = StaticBox("floor", (-20, -1, -20), (20, 0, 20))
GOAL = StaticBox("goal", (15, 0, 15), (18, 3, 18))


def empty_stage(**overrides):
    return replace(Stage("test", (0, 0, 0), (FLOOR,), GOAL, ()), **overrides)


class SaveTests(unittest.TestCase):
    def test_missing_and_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SaveStore(Path(directory) / "profile.json")
            data = store.load()
            self.assertEqual(data, defaults())
            data["meso"] = 400
            purchase(data, "hat_leaf")
            toggle_equip(data, "hat_leaf")
            data["best_time"] = 80.5
            data["options"]["bgm"] = 0.8
            self.assertTrue(store.write(data))
            self.assertEqual(SaveStore(store.path).load(), data)
            self.assertFalse(list(Path(directory).glob("*.tmp")))

    def test_corruption_is_backed_up_and_defaults_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            path.write_text("{broken", encoding="utf-8")
            store = SaveStore(path)
            self.assertEqual(store.load(), defaults())
            self.assertTrue(store.notice)
            self.assertEqual(len(list(Path(directory).glob("save.corrupt-*.json"))), 1)

    def test_settings_are_bounded_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SaveStore(Path(directory) / "save.json")
            game = Session(store)
            game.action("option:bgm:5")
            game.action("option:sfx:-5")
            game.action("option:sensitivity:10")
            game.action("option:shadows:0")
            options = Session(store).profile["options"]
            self.assertEqual(options, {"bgm": 1, "sfx": 0, "sensitivity": 3, "shadows": False})

    def test_invalid_fields_are_sanitized(self):
        data = {"version": 1, "meso": -10, "owned": ["hat_leaf", "hat_leaf", {}, "unknown"],
                "equipped": {"back": "hat_leaf", "hat": "hat_crown"}, "best_time": float("nan"),
                "options": {"bgm": 100, "sfx": -1, "sensitivity": "fast", "shadows": "yes"}}
        result = validate(data)
        self.assertEqual(result["meso"], 0)
        self.assertEqual(result["owned"], ["hat_leaf"])
        self.assertEqual(result["equipped"], {})
        self.assertIsNone(result["best_time"])
        self.assertEqual(result["options"], {"bgm": 1, "sfx": 0, "sensitivity": 1, "shadows": True})

    def test_unknown_version_is_recovered(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            path.write_text(json.dumps({"version": 999}), encoding="utf-8")
            self.assertEqual(SaveStore(path).load(), defaults())

    def test_write_failure_reports_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not-a-directory"
            blocker.write_text("file", encoding="utf-8")
            store = SaveStore(blocker / "save.json")
            self.assertFalse(store.write(defaults()))
            self.assertTrue(store.notice)


class EconomyTests(unittest.TestCase):
    def test_reward_decreases_and_is_bounded(self):
        values = [reward_for(t) for t in (0, 30, 120, 240, 5000)]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertGreaterEqual(min(values), DEFAULTS.base_reward)
        self.assertLessEqual(max(values), DEFAULTS.maximum_reward)

    def test_buy_insufficient_duplicate_and_equipment_slots(self):
        profile = defaults()
        self.assertFalse(purchase(profile, "hat_leaf")[0])
        profile["meso"] = 1000
        for item in ITEMS:
            self.assertTrue(purchase(profile, item.id)[0])
        balance = profile["meso"]
        self.assertFalse(purchase(profile, "hat_leaf")[0])
        self.assertEqual(profile["meso"], balance)
        self.assertTrue(toggle_equip(profile, "hat_leaf")[0])
        self.assertTrue(toggle_equip(profile, "hat_crown")[0])
        self.assertEqual(profile["equipped"]["hat"], "hat_crown")
        toggle_equip(profile, "hat_crown")
        self.assertNotIn("hat", profile["equipped"])
        self.assertFalse(toggle_equip(defaults(), "hat_leaf")[0])

    def test_two_stage_reward_once_and_pause_clock(self):
        profile = defaults()
        game = Progress(profile)
        game.start()
        game.tick(30)
        game.pause()
        game.tick(100)
        self.assertEqual(game.elapsed, 30)
        game.resume()
        game.finish_stage()
        self.assertEqual(game.stage_index, 1)
        self.assertEqual(profile["meso"], 0)
        game.tick(40)
        game.finish_stage()
        self.assertEqual(game.elapsed, 70)
        self.assertEqual(game.screen, Screen.RESULTS)
        balance = profile["meso"]
        self.assertEqual(balance, reward_for(70))
        self.assertFalse(game.finish_stage())
        self.assertEqual(profile["meso"], balance)
        self.assertEqual(profile["best_time"], 70)

    def test_abandon_gives_no_reward(self):
        game = Progress(defaults())
        game.start()
        game.tick(20)
        game.abandon()
        game.finish_stage()
        self.assertEqual(game.profile["meso"], 0)


class WorldTests(unittest.TestCase):
    def test_complete_both_live_courses_using_movement_and_jump_inputs(self):
        for stage in STAGES:
            world = StageWorld(stage)
            p = world.player
            takeoff = np.array(stage.route[0])
            for _ in range(600):
                delta = takeoff[[0, 2]] - p.pos[[0, 2]]
                world.update(1 / 120, delta * 3 / p.settings.move_speed)
                if np.linalg.norm(delta) < 0.08 and p.grounded:
                    break
            for target in stage.route[1:]:
                p.set_jump_held(False)
                p.set_jump_held(True)
                for _ in range(240):
                    delta = np.array(target)[[0, 2]] - p.pos[[0, 2]]
                    world.update(1 / 120, delta * 3 / p.settings.move_speed)
                    if p.grounded or world.completed:
                        break
                self.assertAlmostEqual(p.pos[1], target[1], msg=f"{stage.name}: {target}, hits={p.hit_count}")
            destination = (np.array(stage.goal.lo) + stage.goal.hi) / 2
            for _ in range(300):
                world.update(1 / 120, (destination[[0, 2]] - p.pos[[0, 2]]) * 3 / p.settings.move_speed)
                if world.completed:
                    break
            self.assertTrue(world.completed, stage.name)

    def test_banana_hit_stun_immunity_and_recovery(self):
        world = StageWorld(empty_stage())
        p = world.player
        world.projectiles = [Banana(np.array((-2., 0.7, 0)), np.array((500., 0, 0))) for _ in range(2)]
        world.update(1 / 120)
        self.assertEqual(p.hit_count, 1)
        self.assertEqual(p.state, "stunned")
        self.assertEqual(len(world.projectiles), 0)
        self.assertGreater(p.velocity[0], 0)
        world.update(1.2)
        self.assertEqual(p.state, "grounded")
        self.assertEqual(p.invulnerability_left, 0)

    def test_projectile_removed_by_terrain_and_lifetime(self):
        wall = StaticBox("wall", (-1, 0, -1), (-0.9, 3, 1))
        world = StageWorld(empty_stage(boxes=(FLOOR, wall)))
        world.projectiles = [Banana(np.array((-2., 0.7, 0)), np.array((500., 0, 0)))]
        world.update(1 / 120)
        self.assertEqual(world.player.hit_count, 0)
        self.assertFalse(world.projectiles)
        world.projectiles = [Banana(np.array((10., 10, 10)), np.zeros(3), age=5)]
        world.update(1 / 120)
        self.assertFalse(world.projectiles)

    def test_monkey_warning_aim_and_projectile_limit(self):
        stage = empty_stage(monkeys=(Monkey((3, 2, 0), interval=1),))
        world = StageWorld(stage, settings=replace(DEFAULTS, projectile_limit=1))
        world.update(0.5)
        self.assertTrue(world.warnings[0])
        world.update(0.51)
        self.assertEqual(len(world.projectiles), 1)
        self.assertLess(world.projectiles[0].velocity[0], 0)
        for _ in range(20):
            world.update(0.2)
            self.assertLessEqual(len(world.projectiles), 1)

    def test_spike_boost_not_accumulated_during_immunity(self):
        spike = StaticBox("spike", (-0.5, 0, -0.5), (0.5, 0.3, 0.5))
        world = StageWorld(empty_stage(spikes=(spike,)))
        world.update(1 / 120)
        p = world.player
        self.assertEqual(p.velocity[1], DEFAULTS.spike_impulse)
        self.assertEqual(p.hit_count, 1)
        world.update(0.25)
        self.assertEqual(p.hit_count, 1)
        self.assertGreater(p.pos[1], p.settings.jump_height)

    def test_rope_grab_climb_clamp_and_space_release(self):
        rope = Rope(0, 0, 0, 3)
        world = StageWorld(empty_stage(ropes=(rope,)))
        self.assertTrue(world.grab_rope())
        self.assertEqual(world.player.state, "rope")
        world.update(2, climb=1)
        self.assertEqual(world.player.pos[1], 3)
        world.update(0.2)
        self.assertEqual(world.player.pos[1], 3)
        world.player.set_jump_held(True)
        world.update(1 / 120)
        self.assertIsNone(world.player.rope)
        self.assertGreater(world.player.velocity[1], 0)
        world.player.set_jump_held(True)
        before = world.player.velocity[1]
        world.update(1 / 120)
        self.assertLess(world.player.velocity[1], before)

    def test_rope_down_limit_damage_detaches_and_respawn_cleans_state(self):
        rope = Rope(0, 0, 0, 3)
        world = StageWorld(empty_stage(ropes=(rope,)))
        world.grab_rope()
        world.update(1, climb=-1)
        self.assertEqual(world.player.pos[1], 0)
        p = world.player
        self.assertTrue(p.damage((-1, 0, 0), "바나나"))
        self.assertIsNone(p.rope)
        self.assertFalse(p.damage((-1, 0, 0)))
        p.pos[1] = -20
        world.update(1 / 120)
        self.assertEqual(p.respawn_count, 1)
        self.assertEqual(p.invulnerability_left, 0)
        self.assertEqual(p.knockback_left, 0)
        self.assertIsNone(p.last_hit)
        self.assertIsNone(p.rope)

    def test_camera_clips_against_wall(self):
        camera = GameCamera()
        camera.target[:] = (0, 1, 0)
        camera.pitch = 0.1
        wall = StaticBox("wall", (-5, 0, 3), (5, 6, 3.2))
        camera.boxes = (wall,)
        self.assertLess(camera.eye[2], 2.8)

    def test_camera_focus_lag_cannot_cross_wall(self):
        camera = GameCamera()
        camera.target[:] = (0, 1, 0)
        camera.boxes = (StaticBox("wall", (-5, 0, 3), (5, 6, 3.2)),)
        camera.follow((0, 0, 5), 0.001, height=1)
        self.assertGreater(camera.target[2], 3.4)

    def test_both_course_routes_are_reachable_with_base_jump(self):
        for stage in STAGES:
            for start, target in zip(stage.route, stage.route[1:]):
                p = PlatformerController(stage.boxes, start)
                p.set_jump_held(True)
                for _ in range(240):
                    delta = np.array(target)[[0, 2]] - p.pos[[0, 2]]
                    p.advance(1 / 120, delta * 3 / p.settings.move_speed)
                    if p.grounded:
                        break
                self.assertTrue(p.grounded, (stage.name, target))
                self.assertAlmostEqual(p.pos[1], target[1], msg=f"{stage.name}: {target}")

    def test_stage_spawn_and_goal_are_safe(self):
        for stage in STAGES:
            world = StageWorld(stage)
            p = world.player
            self.assertTrue(p.grounded)
            for hazard in stage.hazards:
                self.assertFalse(hazard.hits(p.pos, p.pos, (0.64, 1.4, 0.64), 0, hazard.period))
            for spike in stage.spikes:
                self.assertFalse(np.all(np.array(stage.spawn) >= spike.lo)
                                 and np.all(np.array(stage.spawn) <= spike.hi))


class SessionTests(unittest.TestCase):
    def test_falling_keeps_clock_and_returns_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Session(SaveStore(Path(directory) / "save.json"))
            game.start()
            p = game.world.player
            p.pos[1] = -20
            p.invulnerability_left = 0.5
            p.knockback_left = 0.1
            game.update(0.1)
            self.assertEqual(p.respawn_count, 1)
            self.assertAlmostEqual(game.progress.elapsed, 0.1)
            self.assertEqual(p.invulnerability_left, 0)
            self.assertEqual(p.knockback_left, 0)
            self.assertTrue(p.grounded)

    def test_full_challenge_with_live_obstacles_at_30fps(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Session(SaveStore(Path(directory) / "save.json"))
            game.start()
            pilot = CoursePilot()
            for _ in range(1500):
                game.update(1 / 30, pilot.controls(game.world))
                if game.progress.screen == Screen.RESULTS:
                    break
            self.assertEqual(game.progress.screen, Screen.RESULTS)
            self.assertEqual(game.progress.stage_index, 1)
            self.assertGreater(game.progress.elapsed, 10)
            self.assertEqual(game.profile["meso"], reward_for(game.progress.elapsed))

    def test_stage_transition_results_shop_save_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SaveStore(Path(directory) / "save.json")
            game = Session(store)
            game.start()
            old = game.world
            old.projectiles.append(Banana(np.array((4., 10, 0)), np.zeros(3)))
            game.world.completed = True
            game.update(0)
            self.assertEqual(game.progress.stage_index, 1)
            self.assertIsNot(game.world, old)
            self.assertFalse(old.projectiles)
            game.world.completed = True
            game.update(0)
            self.assertEqual(game.progress.screen, Screen.RESULTS)
            balance = game.profile["meso"]
            game.update(1)
            self.assertEqual(game.profile["meso"], balance)
            game.lobby()
            game.action("shop")
            game.action("buy:hat_leaf")
            game.action("equip:hat_leaf")
            restored = Session(store)
            self.assertEqual(restored.profile["meso"], balance - 100)
            self.assertEqual(restored.profile["equipped"], {"hat": "hat_leaf"})

    def test_pause_freezes_world_and_clock_and_restarts_are_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Session(SaveStore(Path(directory) / "save.json"))
            for _ in range(5):
                game.start()
                game.update(0.25)
                p = game.world.player
                before = p.pos.copy()
                clock = game.progress.elapsed
                game.progress.pause()
                game.update(50, (1, 1))
                np.testing.assert_array_equal(before, p.pos)
                self.assertEqual(game.progress.elapsed, clock)
                game.action("settings")
                game.update(50)
                self.assertEqual(game.progress.elapsed, clock)
                game.action("back")
                self.assertEqual(game.progress.screen, Screen.PAUSED)
                game.action("resume")
                game.update(0.25)
                self.assertAlmostEqual(game.progress.elapsed, clock + 0.25)
                old = game.world
                game.lobby()
                self.assertIsNone(game.world)
                self.assertFalse(old.projectiles)
                self.assertFalse(old.monkey_clocks)
                self.assertEqual(game.profile["meso"], 0)


class ResourceTests(unittest.TestCase):
    def test_shared_bgm_continues_between_scenes(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = object.__new__(Audio)
            audio.root = Path(directory)
            audio.common_music = audio.root / "WhenTheMorningComes.mp3"
            audio.common_music.write_bytes(b"test")
            audio.enabled = True
            audio.current_music = None
            audio.current_track = None
            with patch("pygame.mixer.stop"), patch("pygame.mixer.music.stop"), \
                 patch("pygame.mixer.music.load") as load, patch("pygame.mixer.music.play") as play:
                audio.music("lobby")
                audio.music("stage1")
                audio.music("stage2")
                load.assert_called_once_with(str(audio.common_music))
                play.assert_called_once_with(-1)
                override = audio.root / "stage1.ogg"
                override.write_bytes(b"test")
                audio.music("stage1")
                self.assertEqual(load.call_count, 2)
                self.assertEqual(audio.current_track, override)

    def test_absent_art_and_bad_model_use_cached_primitives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "platformer").mkdir()
            (root / "platformer/models.json").write_text('{"character":"missing.glb"}', encoding="utf-8")
            renderer = Mock()
            resources = Resources(renderer, root)
            with self.assertLogs(level="WARNING"):
                a = resources.instance("character", (1, 1, 1), "#ffffff")
            b = resources.instance("character", (1, 1, 1), "#ffffff")
            self.assertIs(a.model, b.model)
            self.assertEqual(renderer.upload.call_count, 1)

    def test_material_factors_are_read(self):
        import gltf
        model = object.__new__(gltf.Model)
        model.path = "example.glb"
        model.json = {"materials": [{"pbrMetallicRoughness": {
            "baseColorFactor": [0.1, 0.2, 0.3, 1], "metallicFactor": 0.7, "roughnessFactor": 0.2}}]}
        model._read_materials()
        self.assertEqual(model.materials[0]["metallic"], 0.7)
        self.assertEqual(model.materials[0]["roughness"], 0.2)

    def test_missing_texture_uses_white_and_logs_once(self):
        import pygame
        from renderer import Renderer
        renderer = object.__new__(Renderer)
        renderer.white, renderer.textures = 7, {}
        with patch("pygame.image.load", side_effect=pygame.error("missing")) as load:
            with self.assertLogs(level="WARNING"):
                self.assertEqual(renderer.texture(("file", "missing.png")), 7)
            self.assertEqual(renderer.texture(("file", "missing.png")), 7)
            load.assert_called_once()

    def test_music_switches_once_and_pause_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = object.__new__(Audio)
            audio.root = Path(directory)
            audio.enabled = True
            audio.current_music = None
            with patch("pygame.mixer.stop") as stop, patch("pygame.mixer.music.stop"), \
                 patch("pygame.mixer.pause") as pause, patch("pygame.mixer.music.pause"), \
                 patch("pygame.mixer.unpause") as unpause, patch("pygame.mixer.music.unpause"):
                audio.music("lobby")
                audio.music("lobby")
                audio.music("stage1")
                self.assertEqual(stop.call_count, 2)
                audio.pause(True)
                audio.pause(False)
                pause.assert_called_once()
                unpause.assert_called_once()
