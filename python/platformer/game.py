"""3D Forest of Patience. From python/: uv run python -m platformer."""
import argparse
import logging
from pathlib import Path

import numpy as np
import pygame
from OpenGL.GL import GL_RGB, GL_UNSIGNED_BYTE, glReadPixels

from renderer import Renderer
from .audio import Audio
from .autoplay import CoursePilot
from .camera import GameCamera
from .input import MouseLook
from .progress import Screen
from .resources import Resources
from .save import SaveStore
from .session import Session
from .stages import STAGES
from .ui import UI
from .visuals import StageVisual
from .world import StageWorld


def run(args):
    width, height = 1280, 720
    pygame.display.init()
    pygame.font.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    flags = pygame.OPENGL | pygame.DOUBLEBUF | (pygame.HIDDEN if args.hidden else 0)
    pygame.display.set_mode((width, height), flags)
    pygame.display.set_caption("3D 인내의 숲")
    pygame.key.set_repeat()
    renderer = Renderer(width, height)
    renderer.materials_enabled = True
    renderer.fog = np.array((0.53, 0.72, 0.66))
    resources = Resources(renderer, args.resources)
    session = Session(SaveStore(args.save))
    camera = GameCamera()
    mouse = MouseLook(camera, capture=False)
    ui = UI(renderer, width, height)
    audio = Audio(Path(args.resources) / "audio/platformer" if args.resources else None)
    preview = StageWorld(STAGES[0])
    view_world = preview
    visual = StageVisual(resources, preview)
    camera.target[:] = preview.player.pos + (0, 0.9, 0)
    clock = pygame.time.Clock()
    running, debug = True, args.debug
    frames, scene_key, previous_screen = 0, None, None
    pilot = CoursePilot() if args.autoplay else None
    if args.play or pilot:
        session.start()
    elif args.screen == "paused":
        session.start()
        session.progress.pause()
    elif args.screen != "lobby":
        session.action(args.screen)
    try:
        while running:
            dt = clock.tick(args.fps) / 1000
            if pilot:
                dt = 1 / 30  # reproducible simulation, independent of GPU speed
            for event in pygame.event.get():
                screen = session.progress.screen
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.WINDOWFOCUSLOST:
                    mouse.handle(event)
                    session.progress.pause()
                    if session.world:
                        session.world.player.set_jump_held(False)
                        session.world.player._jump_pending = False
                elif event.type == pygame.WINDOWFOCUSGAINED:
                    mouse.handle(event)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if screen == Screen.PLAYING:
                        session.progress.pause()
                    elif screen == Screen.PAUSED:
                        session.progress.resume()
                    elif screen in (Screen.SETTINGS, Screen.SHOP, Screen.HELP):
                        session.action("back")
                    elif screen == Screen.RESULTS:
                        session.lobby()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_F3:
                    debug = not debug
                elif screen == Screen.PLAYING:
                    mouse.handle(event)
                    player = session.world.player
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_SPACE:
                            player.set_jump_held(True)
                        elif event.key == pygame.K_e:
                            session.world.grab_rope()
                    elif event.type == pygame.KEYUP and event.key == pygame.K_SPACE:
                        player.set_jump_held(False)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    action = ui.click(event.pos)
                    if action == "quit":
                        running = False
                    elif action:
                        old_meso = session.profile["meso"]
                        session.action(action)
                        if session.profile["meso"] < old_meso:
                            audio.play("purchase")
            if not running:
                break
            screen = session.progress.screen
            if screen != previous_screen:
                if screen == Screen.PLAYING:
                    mouse.set_capture(not args.hidden)
                else:
                    mouse.set_capture(False)
                if session.world:
                    session.world.player.set_jump_held(False)
                    session.world.player._jump_pending = False
                previous_screen = screen
            options = session.profile["options"]
            camera.sensitivity = options["sensitivity"]
            renderer.shadows_enabled = options["shadows"]
            audio.volumes(options)
            music_key = f"stage{session.progress.stage_index + 1}" if session.progress.active else "lobby"
            if music_key != scene_key:
                audio.music(music_key)
                scene_key = music_key
            audio.pause(screen in (Screen.PAUSED, Screen.SETTINGS, Screen.HELP) and session.progress.active)
            keys = pygame.key.get_pressed()
            forward = camera.forward_xz()
            right = np.array((-forward[2], 0, forward[0]))
            movement = forward * (int(keys[pygame.K_w]) - int(keys[pygame.K_s]))
            movement += right * (int(keys[pygame.K_d]) - int(keys[pygame.K_a]))
            move = pilot.controls(session.world) if pilot and screen == Screen.PLAYING else movement[[0, 2]]
            session.update(dt, move, int(keys[pygame.K_w]) - int(keys[pygame.K_s]))
            screen = session.progress.screen
            next_music = f"stage{session.progress.stage_index + 1}" if session.progress.active else "lobby"
            if next_music != scene_key:
                audio.music(next_music)
                scene_key = next_music
            desired_world = session.world if session.world is not None else preview
            if desired_world is not view_world:
                view_world = desired_world
                visual = StageVisual(resources, view_world)
                camera.target[:] = view_world.player.pos + (0, 0.9, 0)
                camera.yaw = 0
            if screen == Screen.RESULTS and previous_screen != Screen.RESULTS:
                audio.play("clear")
            for name in view_world.events:
                audio.play(name)
            view_world.events.clear()
            camera.boxes = view_world.stage.boxes
            if screen == Screen.PLAYING:
                camera.follow(view_world.player.pos, dt, height=0.9)
            drawn = visual.sync(dt if screen == Screen.PLAYING else 0, session.profile)
            view, proj = camera.view(), camera.proj(width / height)
            p = view_world.player
            selected = visual.player.body if p.invulnerability_left > 0 else None
            renderer.render(drawn, view, proj, camera.eye, p.pos, selected=selected)
            if p.invulnerability_left > 0 and int(view_world.time * 10) % 2 == 0:
                lo, hi = p.bounds()
                renderer.draw_boxes([(lo - 0.05, hi + 0.05)], view, proj, color=(1, 0.9, 0.45))
            if debug:
                renderer.draw_boxes([(np.array(b.lo), np.array(b.hi)) for b in view_world.stage.boxes]
                                    + [p.bounds()], view, proj)
            ui.draw(session, view_world, clock.get_fps(), debug)
            frames += 1
            if (args.frames and frames >= args.frames) or (pilot and screen == Screen.RESULTS):
                if args.screenshot:
                    pixels = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
                    Path(args.screenshot).parent.mkdir(parents=True, exist_ok=True)
                    pygame.image.save(pygame.image.frombytes(pixels, (width, height), "RGB", True), args.screenshot)
                running = False
            pygame.display.flip()
        print(f"Rendered {frames} frames; screen={session.progress.screen.value}; "
              f"stage={session.progress.stage_index + 1}; time={session.progress.elapsed:.3f}")
    finally:
        mouse.set_capture(False)
        session.save()
        audio.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--hidden", action="store_true")
    parser.add_argument("--screenshot")
    parser.add_argument("--save", help="Override save file path")
    parser.add_argument("--resources", help="Override assets root; an empty directory tests fallback art/audio")
    parser.add_argument("--play", action="store_true", help="Start challenge immediately")
    parser.add_argument("--screen", choices=("lobby", "shop", "settings", "help", "paused"), default="lobby",
                        help="Open a menu for rendering verification")
    parser.add_argument("--autoplay", action="store_true", help="Verify both courses with scripted movement inputs")
    parser.add_argument("--debug", action="store_true")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        run(parser.parse_args())
    finally:
        pygame.quit()
