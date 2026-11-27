"""Scene lifecycle and player-facing actions; usable in headless tests."""
from .inventory import purchase, toggle_equip
from .progress import Progress, Screen
from .stages import STAGES
from .world import StageWorld


class Session:
    def __init__(self, store):
        self.store = store
        self.profile = store.load()
        self.progress = Progress(self.profile)
        self.world = None
        self.message = store.notice
        self.revision = 0

    def save(self):
        if not self.store.write(self.profile):
            self.message = self.store.notice

    def load_stage(self):
        if self.world:
            self.world.dispose()
        self.world = StageWorld(STAGES[self.progress.stage_index])
        self.revision += 1

    def start(self):
        self.progress.start()
        self.load_stage()

    def lobby(self):
        if self.world:
            self.world.dispose()
        self.world = None
        self.progress.abandon()
        self.revision += 1
        self.save()

    def update(self, dt, move=(0, 0), climb=0):
        if self.progress.screen != Screen.PLAYING or self.world is None:
            return
        previous = self.world.time
        self.world.update(dt, move, climb)
        self.progress.tick(self.world.time - previous)
        if self.world.completed:
            self.progress.finish_stage()
            if self.progress.screen == Screen.PLAYING:
                self.load_stage()
            else:
                self.world.dispose()
                self.save()

    def action(self, action):
        progress = self.progress
        if action == "start":
            self.start()
        elif action == "lobby":
            self.lobby()
        elif action == "resume":
            progress.resume()
        elif action in ("shop", "help", "settings"):
            progress.return_screen = progress.screen
            progress.screen = Screen(action)
        elif action == "back":
            progress.screen = progress.return_screen
            self.save()
        elif action.startswith("buy:"):
            _, self.message = purchase(self.profile, action.split(":", 1)[1])
            self.save()
        elif action.startswith("equip:"):
            _, self.message = toggle_equip(self.profile, action.split(":", 1)[1])
            self.save()
        elif action.startswith("option:"):
            _, key, amount = action.split(":")
            if key == "shadows":
                self.profile["options"][key] = not self.profile["options"][key]
            else:
                low, high = (0.2, 3) if key == "sensitivity" else (0, 1)
                self.profile["options"][key] = round(max(low, min(high,
                    self.profile["options"][key] + float(amount))), 2)
            self.save()
