from enum import Enum, IntEnum, StrEnum
from typing import Tuple, Union

import numpy as np
from loguru import logger
from scipy.interpolate import Akima1DInterpolator, CubicSpline

from linearheart.utils.communication import float_to_fixed


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


def coefficient_mapping(
    config: dict, motor_pool: dict, model: Union[Akima1DInterpolator, CubicSpline], encode: bool = True
) -> np.ndarray:
    """
    将相对波形系数映射到绝对波形系数
    :param config:配置文件
    :param motor_pool: 电机池
    :param model: 插值模型
    :param encode: 是否编码后输出，默认为True
    :return:
    """
    motor = motor_pool[config["当前电机"]]

    coefficient_matrix = model.c.T.copy()
    coefficient_matrix *= motor["限位"] - motor["零位"]  # 映射到导轨长度
    coefficient_matrix *= config["幅值比例"]  # 设定幅值
    coefficient_matrix[:, 3] += motor["零位"]  # 零位偏移
    coefficient_matrix[:, 3] += config["偏移量"]  # 设定偏移

    coefficients = np.append(np.column_stack([model.x[:-1], coefficient_matrix]).flatten(), 1)
    logger.debug(f"波形计算完毕，系数矩阵：\n{coefficients}")
    if encode:
        return float_to_fixed(coefficients)
    else:
        return coefficients


def compute_features(points: np.ndarray) -> Tuple[float, float, float, float]:
    """
    运动学特征计算
    :param points : 曲线点集，shape=(N,2)
    :return: (max_velocity, max_acceleration, max_deceleration, jerk)
    """
    if points.ndim != 2:
        raise ValueError("输入必须是N×2的二维数组")

    sorted_idx = np.argsort(points[:, 0])
    t = points[sorted_idx, 0]  # 时间轴
    y = points[sorted_idx, 1]  # 位置量

    # 计算实际时间差
    dt = np.diff(t)
    dt = np.where(dt == 0, 1e-6, dt)  # 避免除零错误

    # 一阶导数：速度
    velocity = np.diff(y) / dt
    max_velocity = np.max(np.abs(velocity)) if velocity.size > 0 else 0.0

    # 二阶导数：加速度
    acceleration = np.diff(velocity) / dt[:-1]
    positive_accel = acceleration[acceleration > 0]  # 加速段
    negative_accel = acceleration[acceleration < 0]  # 减速段
    max_acceleration = positive_accel.max() if positive_accel.size > 0 else 0.0
    max_deceleration = negative_accel.min() if negative_accel.size > 0 else 0.0

    # 三阶导数：加加速度（jerk）
    jerk = np.diff(acceleration) / dt[:-2]
    max_jerk = np.max(np.abs(jerk)) if jerk.size > 0 else 0.0

    return max_velocity, max_acceleration, max_deceleration, max_jerk
