"""Orbit camera with a swept safety volume against stage geometry."""
import numpy as np

from camera import FollowCamera, look_at
from .world import sweep_fraction


class GameCamera(FollowCamera):
    def __init__(self):
        super().__init__(yaw=0, pitch=0.53, dist=10)
        self.sensitivity = 1
        self.boxes = ()

    def rotate(self, dx, dy):
        super().rotate(dx * self.sensitivity, dy * self.sensitivity)

    def follow(self, p, dt, height=0.9):
        super().follow(p, dt, height)
        # The smoothed focus can lag through a wall even if the player is safe.
        # Clip that segment first, then clip the orbit arm in eye().
        anchor = np.asarray(p, float) + (0, height, 0)
        fraction = 1.0
        for box in self.boxes:
            hit = sweep_fraction(anchor, self.target, np.array(box.lo) - 0.22,
                                 np.array(box.hi) + 0.22)
            if hit is not None:
                fraction = min(fraction, max(0, hit - 0.025))
        self.target[:] = anchor + (self.target - anchor) * fraction

    @property
    def eye(self):
        desired = super().eye
        fraction = 1.0
        for box in self.boxes:
            hit = sweep_fraction(self.target, desired, np.array(box.lo) - 0.22,
                                 np.array(box.hi) + 0.22)
            if hit is not None:
                fraction = min(fraction, max(0.02, hit - 0.025))
        return self.target + (desired - self.target) * fraction

    def view(self):
        return look_at(self.eye, self.target)
