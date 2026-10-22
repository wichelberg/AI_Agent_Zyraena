"""glow.frame_geometry: the light's frame is one rounded rectangle, so it has no seams at the corners.

Run from the project folder: python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import glow  # noqa: E402

W, H, R = 1680, 1050, 115


def around(dist):
    """Pixel centres on the loop `dist` px in from the screen's edges (corners rounded), in order."""
    pts = []
    for x in np.arange(R, W - R):
        pts.append((x, dist))
    for k in np.linspace(0, np.pi / 2, 60):
        pts.append((W - R + (R - dist) * np.sin(k), R - (R - dist) * np.cos(k)))
    for y in np.arange(R, H - R):
        pts.append((W - dist, y))
    for k in np.linspace(0, np.pi / 2, 60):
        pts.append((W - R + (R - dist) * np.cos(k), H - R + (R - dist) * np.sin(k)))
    for x in np.arange(W - R, R, -1):
        pts.append((x, H - dist))
    for k in np.linspace(0, np.pi / 2, 60):
        pts.append((R - (R - dist) * np.sin(k), H - R + (R - dist) * np.cos(k)))
    for y in np.arange(H - R, R, -1):
        pts.append((dist, y))
    for k in np.linspace(0, np.pi / 2, 60):
        pts.append((R - (R - dist) * np.cos(k), R - (R - dist) * np.sin(k)))
    return np.array(pts)


class FrameGeometryTest(unittest.TestCase):
    def test_place_along_the_frame_never_jumps(self):
        for dist in (2, 30, 90):
            pts = around(dist)
            p, d = glow.frame_geometry(pts[:, 0], pts[:, 1], W, H, R)
            step = np.diff(p)
            step = (step + 0.5) % 1.0 - 0.5          # across the wrap at the top-left corner
            self.assertLess(np.abs(step).max(), 0.002, dist)
            self.assertTrue(np.all(step >= -1e-9), dist)     # clockwise all the way round
            np.testing.assert_allclose(d, dist, atol=0.6)

    def test_edges_are_at_distance_zero_and_the_middle_is_far(self):
        p, d = glow.frame_geometry(np.array([W / 2, W - 0.5, W / 2, 0.5]), np.array([0.5, H / 2, H - 0.5, H / 2]),
                                   W, H, R)
        np.testing.assert_allclose(d, 0.5)
        np.testing.assert_allclose(p, [0.125 + 0.0, 0.375, 0.625, 0.875], atol=0.08)
        _, mid = glow.frame_geometry(np.array([W / 2]), np.array([H / 2]), W, H, R)
        self.assertGreater(mid[0], 400)

    def test_beyond_a_corner_arc_is_negative(self):
        _, d = glow.frame_geometry(np.array([0.5]), np.array([0.5]), W, H, R)
        self.assertLess(d[0], 0)


if __name__ == "__main__":
    unittest.main()
