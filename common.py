import enum

from scipy.interpolate import Akima1DInterpolator, CubicSpline


class Interpolation(enum.Enum):
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
    Status = 0x2000
    Length = 0x2001
    Error = 0x2002
    Power = 0x2003
    Home = 0x2004
    Coefficient = 0x2010
