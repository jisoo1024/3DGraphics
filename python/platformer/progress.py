"""Explicit screen transitions, challenge clock and once-only rewards."""
from enum import Enum

from .config import DEFAULTS


class Screen(str, Enum):
    LOBBY = "lobby"
    PLAYING = "playing"
    PAUSED = "paused"
    RESULTS = "results"
    SHOP = "shop"
    SETTINGS = "settings"
    HELP = "help"


def reward_for(seconds, settings=DEFAULTS):
    bonus = max(0, settings.bonus_seconds - max(0, seconds)) * settings.bonus_per_second
    return min(settings.maximum_reward, settings.base_reward + int(bonus))


class Progress:
    def __init__(self, profile):
        self.profile = profile
        self.screen = Screen.LOBBY
        self.stage_index = 0
        self.elapsed = 0.0
        self.reward = 0
        self.reward_paid = False
        self.active = False
        self.return_screen = Screen.LOBBY

    def start(self):
        self.stage_index, self.elapsed, self.reward = 0, 0.0, 0
        self.reward_paid = False
        self.active = True
        self.screen = Screen.PLAYING

    def tick(self, dt):
        if self.screen == Screen.PLAYING and self.active:
            self.elapsed += dt

    def pause(self):
        if self.screen == Screen.PLAYING:
            self.screen = Screen.PAUSED

    def resume(self):
        if self.screen == Screen.PAUSED:
            self.screen = Screen.PLAYING

    def abandon(self):
        self.active = False
        self.screen = Screen.LOBBY

    def finish_stage(self):
        if not self.active or self.screen != Screen.PLAYING:
            return False
        if self.stage_index == 0:
            self.stage_index = 1
            return True
        if not self.reward_paid:
            self.reward = reward_for(self.elapsed)
            self.profile["meso"] += self.reward
            best = self.profile["best_time"]
            self.profile["best_time"] = self.elapsed if best is None else min(best, self.elapsed)
            self.reward_paid = True
        self.active = False
        self.screen = Screen.RESULTS
        return True
