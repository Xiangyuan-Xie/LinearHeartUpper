import bisect
import unittest
from typing import Tuple, Union

import numpy as np
from scipy.interpolate import Akima1DInterpolator, CubicSpline

from linearheart.common.common import coefficient_mapping, waveform_mapping
from linearheart.utils.communication import fixed_to_float

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


def generate_waveform(
    ModelClass: Union[type[Akima1DInterpolator], type[CubicSpline]], translate: bool = False
) -> Tuple[np.ndarray, np.ndarray]:
    timestamps = np.linspace(0, 1, 501)

    points = np.array(config["插值点集"])
    model = ModelClass(points[:, 0], points[:, 1])

    # 虚拟波形
    mock_waveform = waveform_mapping(config, motor_pool, np.column_stack((timestamps, model(timestamps))))

    # 实际波形
    real_waveform = np.column_stack((timestamps, np.zeros_like(timestamps)))
    if translate:
        encoded_coefficients = coefficient_mapping(config, motor_pool, model, encode=True)
        coefficients = fixed_to_float(encoded_coefficients)
    else:
        coefficients = coefficient_mapping(config, motor_pool, model, encode=False)
    right_nodes = [coefficients[j * 5] for j in range(len(model.x) - 1)]
    for i, timestamp in enumerate(timestamps):
        j = bisect.bisect_right(right_nodes, timestamp) - 1
        k = j * 5
        x0, x1 = coefficients[k], coefficients[k + 5]
        if x0 <= timestamp <= x1:
            a, b, c, d = coefficients[k + 1 : k + 5]
            h = timestamp - x0
            real_waveform[i][1] = a * pow(h, 3) + b * pow(h, 2) + c * h + d

    return mock_waveform, real_waveform


class TestWaveform(unittest.TestCase):
    def test_akima_waveform(self):
        mock_waveform, real_waveform = generate_waveform(Akima1DInterpolator)
        assert mock_waveform.shape == real_waveform.shape, f"虚拟波形和实际波形维度不一致"
        assert np.allclose(mock_waveform, real_waveform, atol=1e-6), f"虚拟波形和实际波形存在误差"

    def test_translated_akima_waveform(self):
        mock_waveform, real_waveform = generate_waveform(Akima1DInterpolator, translate=True)
        assert mock_waveform.shape == real_waveform.shape, f"虚拟波形和实际波形维度不一致"
        assert np.allclose(mock_waveform, real_waveform, atol=1e-3), f"虚拟波形和实际波形存在误差"

    def test_cubicspline_waveform(self):
        mock_waveform, real_waveform = generate_waveform(CubicSpline)
        assert mock_waveform.shape == real_waveform.shape, f"虚拟波形和实际波形维度不一致"
        assert np.allclose(mock_waveform, real_waveform, atol=1e-6), f"虚拟波形和实际波形存在误差"

    def test_translated_cubicspline_waveform(self):
        mock_waveform, real_waveform = generate_waveform(CubicSpline, translate=True)
        assert mock_waveform.shape == real_waveform.shape, f"虚拟波形和实际波形维度不一致"
        assert np.allclose(mock_waveform, real_waveform, atol=1e-3), f"虚拟波形和实际波形存在误差"
