import unittest

import numpy as np
from scipy.interpolate import Akima1DInterpolator

from linearheart.common.common import coefficient_mapping
from linearheart.utils.communication import fixed_to_float, float_to_fixed

tolerance = 1e-4
config = {
    "插值点集": [
        (0.0, 0.0),
        (0.25925925925925924, 0.391304347826087),
        (0.5577503429355282, 0.6347826086956521),
        (0.7958847736625515, 0.33478260869565185),
        (1.0, 0.0),
    ],
    "偏移量": 0.0,
    "频率": 1.0,
    "幅值比例": 1.0,
    "当前电机": "1号电机",
}
motor_pool = {"1号电机": {"零位": 0.0, "限位": 50.0}}


class TestDataTranslation(unittest.TestCase):
    def setUp(self):
        x_vals, y_vals = zip(*config["插值点集"])
        self.model = Akima1DInterpolator(x_vals, y_vals)
        self.original = coefficient_mapping(config, motor_pool, self.model, encode=False)

    def test_translation(self):
        encoded = float_to_fixed(self.original)
        decoded = fixed_to_float(encoded)
        assert np.allclose(self.original, decoded, atol=1e-3), f"转换前后存在误差"

    def test_internal_translation(self):
        encoded = coefficient_mapping(config, motor_pool, self.model, encode=True)
        decoded = fixed_to_float(encoded)
        assert np.allclose(self.original, decoded, atol=1e-3), f"转换前后存在误差"
