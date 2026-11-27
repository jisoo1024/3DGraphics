"""Optional GLB replacement, bounds fitting, cached procedural fallbacks."""
import json
import logging
from pathlib import Path

import numpy as np

import gltf
from camera import rotate_y, translate
from scene import Instance, ROOT
from .geometry import BoxModel


class FittedInstance(Instance):
    def __init__(self, model, size, pos):
        super().__init__(model, pos)
        lo, hi = model.bounds
        self.fit = np.array(size) / np.maximum(hi - lo, 0.001)
        self.center = (lo + hi) / 2

    def matrix(self):
        return (translate(*self.pos) @ rotate_y(self.heading)
                @ np.diag([*self.fit, 1]) @ translate(*(-self.center)))


class Resources:
    def __init__(self, renderer, root=None):
        self.renderer = renderer
        self.root = Path(root) if root else Path(ROOT) / "assets"
        self.models = {}
        self.primitives = {}
        self.manifest = {}
        manifest = self.root / "platformer" / "models.json"
        if manifest.exists():
            try:
                value = json.loads(manifest.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    self.manifest = value
            except (ValueError, OSError) as error:
                logging.warning("Invalid model manifest: %s", error)

    def instance(self, role, size, color, pos=(0, 0, 0)):
        path = self.manifest.get(role)
        if isinstance(path, str) and role not in self.models:
            try:
                model = gltf.Model(str(self.root / "models" / path))
                if any(len(skin["joints"]) > 32 for skin in model.skins):
                    raise ValueError("At most 32 joints per skin are supported")
                self.renderer.upload(model)
                self.models[role] = model
            except Exception as error:
                logging.warning("Model %s (%s): using primitive fallback: %s", role, path, error)
                self.models[role] = None
        model = self.models.get(role)
        if model is not None:
            return FittedInstance(model, size, pos)
        key = (tuple(size), color)
        if key not in self.primitives:
            self.primitives[key] = BoxModel(size, color)
            self.renderer.upload(self.primitives[key])
        return Instance(self.primitives[key], pos)
