import unittest

import numpy as np
from rasterio.transform import from_origin
from shapely.geometry import box

from fetch_wapor import enclosing_window
from serve import parse_filters
from zonal import aggregate, projected_edges


class AtlasTest(unittest.TestCase):
    def setUp(self):
        self.affine = from_origin(-6.5, 35, 0.01, 0.01)
        xs, ys = projected_edges(self.affine, 2, 1)
        self.zone = box((xs[0] + xs[1]) / 2 + (xs[1] - xs[0]) / 10, ys[1], xs[2], ys[0])

    def test_area_weights_count_partial_cells(self):
        image = np.ma.array([[100.0, 240.0]])
        actual, pixels = aggregate(image, self.affine, self.zone, 0.1)
        self.assertAlmostEqual(actual["weighted"], (4 * 10 + 10 * 24) / 14)
        self.assertAlmostEqual(actual["coverage"], 1)
        self.assertEqual(actual["centroid"], 24)
        self.assertEqual(actual["cell_center"], 24)
        self.assertEqual(len(pixels), 2)

    def test_mask_fraction_keeps_full_polygon_denominator(self):
        image = np.ma.array([[100.0, 240.0]], mask=[[True, False]])
        actual, _ = aggregate(image, self.affine, self.zone, 0.1)
        self.assertAlmostEqual(actual["coverage"], 10 / 14)
        self.assertEqual(actual["weighted"], 24)
        image.mask = [[True, True]]
        empty, pixels = aggregate(image, self.affine, self.zone, 0.1)
        self.assertEqual((empty["coverage"], empty["weighted"], empty["centroid"], pixels), (0, None, None, []))

    def test_clipped_window_is_rejected(self):
        image = np.ma.array([[100.0, 240.0]])
        with self.assertRaisesRegex(ValueError, "extends"):
            aggregate(image, self.affine, self.zone.buffer(10), 0.1)

    def test_acquisition_rounds_both_sides_outward(self):
        window = enclosing_window((-6.498, 34.989, -6.481, 34.997), self.affine)
        self.assertEqual(window.flatten(), (0, 0, 2, 2))

    def test_filters_reject_unknown_duplicate_and_missing_values(self):
        self.assertEqual(parse_filters("year=2023&level=L2&indicator=GBWP"), (2023, "L2", "GBWP"))
        for query in ("year=2025&level=L2&indicator=GBWP", "year=2023&level=L2&level=L1&indicator=GBWP",
                      "level=L2&indicator=GBWP", "year=2023&level=L2&indicator=AETI&debug=1"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                parse_filters(query)
