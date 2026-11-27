"""Optional user-supplied audio, otherwise short locally synthesized effects."""
import logging
from pathlib import Path

import numpy as np
import pygame

from scene import ROOT


class Audio:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(ROOT) / "assets" / "audio" / "platformer"
        self.enabled = False
        self.current_music = None
        self.current_track = None
        # A shared user-provided track plays continuously across game scenes.
        # An explicit resource root remains isolated for missing-resource tests.
        self.common_music = Path(ROOT) / "assets/sounds/WhenTheMorningComes.mp3" if root is None else None
        self.sounds = {}
        self.bgm, self.sfx = 0.35, 0.65
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2)
            self.enabled = True
            frequencies = {"jump": 620, "land": 180, "hit": 100, "purchase": 900,
                           "clear": 1200, "throw": 300, "respawn": 230}
            rate, _, channels = pygame.mixer.get_init()
            for name, frequency in frequencies.items():
                path = self.root / f"{name}.wav"
                try:
                    if path.exists():
                        self.sounds[name] = pygame.mixer.Sound(str(path))
                    else:
                        raise FileNotFoundError(path)
                except (pygame.error, OSError):
                    if path.exists():
                        logging.warning("Cannot load effect %s; using generated tone", path)
                    t = np.arange(int(rate * 0.12)) / rate
                    wave = (np.sin(2 * np.pi * frequency * t) * np.exp(-30 * t) * 6000).astype(np.int16)
                    samples = np.repeat(wave[:, None], channels, axis=1) if channels > 1 else wave
                    self.sounds[name] = pygame.sndarray.make_sound(np.ascontiguousarray(samples))
        except (pygame.error, OSError) as error:
            logging.warning("Audio disabled: %s", error)

    def volumes(self, options):
        self.bgm, self.sfx = options["bgm"], options["sfx"]
        if self.enabled:
            pygame.mixer.music.set_volume(self.bgm)

    def music(self, scene):
        if not self.enabled or scene == self.current_music:
            return
        pygame.mixer.stop()
        self.current_music = scene
        candidates = [self.root / f"{scene}{extension}" for extension in (".ogg", ".wav", ".mp3")]
        common = getattr(self, "common_music", None)
        if common is not None:
            candidates.append(common)
        candidates = [path for path in candidates if path.exists()]
        if (candidates[0] if candidates else None) == getattr(self, "current_track", None):
            return
        pygame.mixer.music.stop()
        self.current_track = None
        for path in candidates:
            try:
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.play(-1)
                self.current_track = path
                logging.info("Playing BGM: %s", path)
                break
            except (pygame.error, OSError) as error:
                logging.warning("Cannot load BGM %s: %s", path, error)

    def play(self, name):
        if self.enabled and name in self.sounds:
            self.sounds[name].set_volume(self.sfx)
            self.sounds[name].play()

    def pause(self, paused):
        if self.enabled:
            if paused:
                pygame.mixer.pause()
                pygame.mixer.music.pause()
            else:
                pygame.mixer.unpause()
                pygame.mixer.music.unpause()

    def close(self):
        if self.enabled:
            pygame.mixer.stop()
            pygame.mixer.music.stop()
