"""Mouse capture and automatic orbit controls for the platformer scene."""
import pygame


class MouseLook:
    def __init__(self, camera, capture=True):
        self.camera = camera
        self.captured = False
        self.focused = True
        self.set_capture(capture)

    def set_capture(self, enabled):
        self.captured = bool(enabled and self.focused)
        pygame.event.set_grab(self.captured)
        pygame.mouse.set_visible(not self.captured)
        pygame.mouse.get_rel()  # discard stale deltas when capture changes

    def handle(self, event):
        if event.type == pygame.WINDOWFOCUSLOST:
            self.focused = False
            self.set_capture(False)
        elif event.type == pygame.WINDOWFOCUSGAINED:
            self.focused = True
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            self.set_capture(not self.captured)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.set_capture(True)
        elif event.type == pygame.MOUSEMOTION and self.captured:
            self.camera.rotate(*event.rel)
        elif event.type == pygame.MOUSEWHEEL and self.focused:
            self.camera.zoom(event.y)
