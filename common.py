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


class RegisterAddress:
    # 线圈
    class Coil(IntEnum):
        PowerOn = 0
        PowerOff = 1
        Reset = 2
        Start = 3
        Stop = 4
        isWrite = 5

    # 输入寄存器
    class Input(IntEnum):
        Status = 0
        Position = 1

    # 保持寄存器
    class Holding(IntEnum):
        TargetPos = 0
        NumberOfInterval = 2
        Frequency = 3
        Coefficients = 5


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
