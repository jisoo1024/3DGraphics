"""Procedural fallback meshes compatible with the shared glTF renderer."""
import numpy as np

from scene import PlaneModel, srgb_hex_to_linear


class BoxModel(PlaneModel):
    def __init__(self, size, color):
        super().__init__(1, srgb_hex_to_linear(color))
        self.name = "primitive-box"
        half = np.asarray(size, float) / 2
        vertices, normals, indices = [], [], []
        for axis in range(3):
            u, v = (axis + 1) % 3, (axis + 2) % 3
            for sign in (-1, 1):
                normal = np.zeros(3)
                normal[axis] = sign
                start = len(vertices)
                for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    p = np.zeros(3)
                    p[axis], p[u], p[v] = sign, a, b * sign
                    vertices.append(p * half)
                    normals.append(normal)
                indices.extend(start + i for i in (0, 1, 2, 0, 2, 3))
        pr = self.meshes[0][0]
        pr.position = np.asarray(vertices, np.float32)
        pr.normal = np.asarray(normals, np.float32)
        pr.uv = np.zeros((24, 2), np.float32)
        pr.indices = np.asarray(indices, np.uint32)
        self.bounds = (-half, half)
