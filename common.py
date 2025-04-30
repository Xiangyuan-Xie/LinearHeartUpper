from enum import Enum, IntEnum, StrEnum
from typing import Tuple

import numpy as np
from PySide6.QtCore import QThreadPool
from scipy.interpolate import Akima1DInterpolator, CubicSpline


class Interpolation(Enum):
    Akima = 0
    CubicSpline = 1


class InterpolationManager:
    @staticmethod
    def get_name(type: Interpolation):
        if type == Interpolation.Akima:
            return "Akima"
        elif type == Interpolation.CubicSpline:
            return "CubicSpline"
        else:
            raise ValueError("未知的插值方法！")

    @staticmethod
    def get_class(type: Interpolation | str):
        if type == Interpolation.Akima or type == "Akima":
            return Akima1DInterpolator
        elif type == Interpolation.CubicSpline or type == "CubicSpline":
            return CubicSpline
        else:
            raise ValueError("未知的插值方法！")


class RegisterAddress:
    # 线圈
    class Coil(IntEnum):
        PowerOn = 0
        PowerOff = 1
        Reset = 2
        Start = 3
        Stop = 4
        isWriteCoefficients = 5
        isWriteTarget = 6

    # 输入寄存器
    class Input(IntEnum):
        Status = 0
        Header = 1
        Position_Start = 2

    # 保持寄存器
    class Holding(IntEnum):
        TargetPos = 0
        Tailer = 2
        NumberOfInterval = 3
        Frequency = 4
        Coefficients = 6


class MotorPowerStatus(StrEnum):
    PowerOn = "启动"
    PowerOff = "断电"


class MotorOperationStatus(StrEnum):
    Start = "开始运行"
    Stop = "停止运行"


class ConnectionStatus(StrEnum):
    Disconnected = "未连接"
    Connecting = "连接中..."
    Connected = "已连接"


def waveform_mapping(config: dict, motor_pool: dict, points: np.ndarray) -> np.ndarray:
    """
    将相对波形点集映射到绝对波形点集
    :param config: 配置文件
    :param motor_pool: 电机池
    :param points: 曲线点集
    :return: 映射后的曲线点集
    """
    motor = motor_pool[config["当前电机"]]
    zero_pos, limit_pos = motor["零位"], motor["限位"]
    frequency, scale, offset = config["频率"], config["幅值比例"], config["偏移量"]

    mapping_points = points.copy()
    mapping_points[:, 0] /= frequency
    mapping_points[:, 1] = (mapping_points[:, 1] * (limit_pos - zero_pos) - zero_pos) * scale + offset
    return np.clip(mapping_points, zero_pos, limit_pos)


def compute_features(points: np.ndarray) -> Tuple[float, float, float]:
    """
    运动学特征计算
    :param points : 曲线点集，shape=(N,2)
    :return: (velocity, acceleration, jerk)
    """
    if points.ndim != 2:
        raise ValueError("输入必须是N×2的二维数组")

    # 按x列排序并解构
    sorted_idx = np.argsort(points[:, 0])
    x = points[sorted_idx, 0]
    y = points[sorted_idx, 1]

    # 速度
    delta_y = np.abs(np.diff(y))
    max_abs_delta = delta_y.max() if delta_y.size > 0 else 0.0

    # 加速度
    non_zero_mask = y != 0
    if np.any(non_zero_mask):
        reciprocals = 1.0 / y[non_zero_mask]
        max_abs_reciprocal = np.abs(reciprocals).max()
    else:
        max_abs_reciprocal = 0.0

    # 加加速度
    d2y = np.zeros_like(y)
    dx = np.diff(x)
    if np.allclose(dx, dx[0], atol=1e-6):  # 均匀网格
        h = dx[0]
        d2y[1:-1] = (y[2:] - 2 * y[1:-1] + y[:-2]) / h ** 2
    else:  # 非均匀网格
        h_prev = x[1:-1] - x[:-2]
        h_next = x[2:] - x[1:-1]
        dy_prev = (y[1:-1] - y[:-2]) / h_prev
        dy_next = (y[2:] - y[1:-1]) / h_next
        d2y[1:-1] = 2 * (dy_next - dy_prev) / (h_prev + h_next)
    max_abs_d2y = np.abs(d2y).max()

    return max_abs_delta, max_abs_reciprocal, max_abs_d2y
