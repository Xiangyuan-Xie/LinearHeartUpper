from enum import Enum, IntEnum, StrEnum

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


class RegisterAddress(IntEnum):
    Status = 0x6000  # 运行状态寄存器
    ErrorCode = 0x6001  # 错误码寄存器
    Power = 0x6002  # 电源状态寄存器
    Position = 0x6003  # 位置寄存器(0x6003/0x6004)
    Frequency = 0x7000  # 频率寄存器(0x7000/0x7001)
    NumberOfInterval = 0x7002  # 区间数量寄存器
    Coefficients = 0x7003  # 系数寄存器


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
