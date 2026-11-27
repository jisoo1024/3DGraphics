"""Preserved prototype and primitive mesh builder (the full game is in game.py).

Run: uv run python -m platformer.demo (from python/). The original main.py is unchanged.
"""
import argparse

import numpy as np
import pygame
from OpenGL.GL import *  # noqa: F401,F403 -- same convention as renderer.py

from camera import FollowCamera
from .controller import MovementSettings, PlatformerController
from .input import MouseLook
from .level import BOXES, HAZARDS, SPAWN
from renderer import Program, Renderer
from scene import Instance
from .geometry import BoxModel


class PlayerVisual:
    """Render-only adapter. Replace instances with a GLB without changing physics.

    A future GLB should use a feet-centred origin and a suitable visual scale.
    The controller remains an axis-aligned box even if the model rotates.
    """

    def __init__(self, settings):
        self.settings = settings
        self.body = Instance(BoxModel((settings.half_width * 2,
                                       settings.height, settings.half_width * 2), "#f2d685"))
        self.face = Instance(BoxModel((0.35, 0.18, 0.025), "#35474f"))
        self.instances = [self.body, self.face]

    def sync(self, controller):
        self.body.pos[:] = controller.pos + (0, self.settings.height / 2, 0)
        self.face.pos[:] = controller.pos + (0, self.settings.height * 0.78,
                                            self.settings.half_width + 0.016)


class HUD:
    """Pygame font surface uploaded to a small OpenGL overlay texture."""

    def __init__(self, renderer):
        self.font = pygame.font.Font(None, 25)
        self.surface = pygame.Surface((760, 188), pygame.SRCALPHA)
        self.program = Program("""#version 330 core
out vec2 uv;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    uv = p; gl_Position = vec4(p * 2.0 - 1.0, 0, 1);
}""", """#version 330 core
in vec2 uv; out vec4 frag; uniform sampler2D text_tex;
void main() { frag = texture(text_tex, vec2(uv.x, 1.0 - uv.y)); }
""")
        self.vao = glGenVertexArrays(1)
        self.texture = renderer._texture_from_rgba(
            np.zeros((188, 760, 4), np.uint8))

    def draw(self, player, fps, width, height, mouse_look):
        self.surface.fill((21, 33, 36, 230))
        lines = ["3D FOREST OF PATIENCE | WASD: move  Space: jump  Esc: quit",
                 "Mouse: look  Tab: release/capture cursor  Wheel: zoom  B: boxes",
                 f"Grounded: {player.grounded}    Vertical speed: {player.velocity[1]:+.2f} m/s",
                 f"Feet Y: {player.pos[1]:.2f}    Resets: {player.respawn_count}    FPS: {fps:.0f}",
                 f"Hits: {player.hit_count}   Protection: {player.invulnerability_left:.1f}s   "
                 + ("Mouse captured" if mouse_look.captured else "Click to capture mouse"),
                 (f"HIT: {player.last_hit} - knocked back!"
                  if player.invulnerability_left > 0 else
                  "Pink: moving hazards (touch = knockback)  |  Blue: head test")]
        for i, line in enumerate(lines):
            self.surface.blit(self.font.render(line, True, (240, 244, 225)), (12, 10 + i * 28))
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.texture)
        data = pygame.image.tobytes(self.surface, "RGBA")
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 760, 188, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glViewport(12, height - 200, 760, 188)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glUseProgram(self.program.id)
        self.program.i("text_tex", 0)
        glBindVertexArray(self.vao)
        glDrawArrays(GL_TRIANGLES, 0, 3)
        glBindVertexArray(0)
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glViewport(0, 0, width, height)


def run(args):
    width, height = 1280, 720
    pygame.display.init()
    pygame.font.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    flags = pygame.OPENGL | pygame.DOUBLEBUF
    if args.hidden:
        flags |= pygame.HIDDEN
    pygame.display.set_mode((width, height), flags)
    pygame.display.set_caption("3D 인내의 숲 — 이동·점프 테스트")
    pygame.key.set_repeat()  # KEYDOWN only on press, not operating-system repeat
    renderer = Renderer(width, height)
    settings = MovementSettings()  # All movement tuning lives in this dataclass.
    player = PlatformerController(BOXES, SPAWN, settings, hazards=HAZARDS)
    visual = PlayerVisual(settings)
    scene = []
    for box in BOXES:
        lo, hi = np.array(box.lo), np.array(box.hi)
        scene.append(Instance(BoxModel(hi - lo, box.color), (lo + hi) / 2))
    hazard_instances = [Instance(BoxModel(h.size, h.color), h.position(0)) for h in HAZARDS]
    instances = scene + hazard_instances + visual.instances
    for inst in instances:
        renderer.upload(inst.model)
    camera = FollowCamera(yaw=0.18, pitch=0.62, dist=13)
    camera.target[:] = player.pos + (0, 1, -2)
    mouse_look = MouseLook(camera, capture=not args.hidden)
    hud = HUD(renderer)
    clock = pygame.time.Clock()
    running, show_boxes, jump_held = True, False, False
    frames = 0
    while running:
        dt = clock.tick(args.fps) / 1000
        for event in pygame.event.get():
            mouse_look.handle(event)
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_b:
                    show_boxes = not show_boxes
                elif event.key == pygame.K_SPACE:
                    jump_held = True
                    player.set_jump_held(True)
            elif event.type == pygame.KEYUP and event.key == pygame.K_SPACE:
                jump_held = False
                player.set_jump_held(False)
            elif event.type == pygame.WINDOWFOCUSLOST:
                jump_held = False
                player.set_jump_held(False)
        if not running:
            break
        keys = pygame.key.get_pressed()
        forward = camera.forward_xz()
        right = np.array([-forward[2], 0, forward[0]])
        move = forward * (int(keys[pygame.K_w]) - int(keys[pygame.K_s]))
        move += right * (int(keys[pygame.K_d]) - int(keys[pygame.K_a]))
        player.set_jump_held(jump_held)
        if mouse_look.focused:
            player.advance(dt, move[[0, 2]])
        visual.sync(player)
        for hazard, inst in zip(HAZARDS, hazard_instances):
            inst.pos[:] = hazard.position(player.simulation_time)
        # Blink during hit protection, leaving collision/debug volumes stable.
        blink_off = player.invulnerability_left > 0 and int(player.simulation_time * 12) % 2
        drawn = scene + hazard_instances + ([] if blink_off else visual.instances)
        camera.follow(player.pos + (0, 0, -2), dt, height=1)
        view, proj = camera.view(), camera.proj(width / height)
        renderer.render(drawn, view, proj, camera.eye, player.pos)
        if show_boxes:
            renderer.draw_boxes([(np.array(b.lo), np.array(b.hi)) for b in BOXES]
                                + [h.bounds(player.simulation_time) for h in HAZARDS]
                                + [player.bounds()], view, proj)
        hud.draw(player, clock.get_fps(), width, height, mouse_look)
        frames += 1
        if args.frames and frames >= args.frames:
            if args.screenshot:
                pixels = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
                image = pygame.image.frombytes(pixels, (width, height), "RGB", True)
                pygame.image.save(image, args.screenshot)
            running = False
        pygame.display.flip()
    mouse_look.set_capture(False)
    print(f"Rendered {frames} frames; grounded={player.grounded}; "
          f"y={player.pos[1]:.3f}; hits={player.hit_count}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fps", type=int, default=60, help="Render cap; try 5 to test slow frames")
    parser.add_argument("--frames", type=int, default=0, help="Exit after N frames (0: interactive)")
    parser.add_argument("--hidden", action="store_true", help="Hidden window for rendering smoke test")
    parser.add_argument("--screenshot", help="Save last frame when --frames is used")
    try:
        run(parser.parse_args())
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
