import pickle
from typing import Any, List, Sequence

import numpy as np
import pandas as pd
from pymodbus.client import ModbusTcpClient
from PySide6.QtCore import QDir, QObject, QRunnable, Signal
from scipy.interpolate import Akima1DInterpolator, CubicSpline

from linearheart.common.common import (
    Interpolation,
    InterpolationManager,
    waveform_mapping,
)


class TaskRunner(QRunnable):
    def __init__(self, task):
        super().__init__()
        self.task = task

    def run(self):
        self.task.run()  # 调用任务类的 run 方法


class ExpressionTask(QObject):
    result = Signal(Any, str, str)

    def __init__(self, points: Sequence[Sequence[float]], offset: float, amplitude: float, method: Interpolation):
        super().__init__()
        self.points = sorted(points, key=lambda p: p[0])
        self.offset = offset
        self.amplitude = amplitude
        self.method = method

    @staticmethod
    def generate_akima_latex(x_vals, y_vals):
        """
        生成Akima插值表达式
        """
        poly = Akima1DInterpolator(x_vals, y_vals)
        case_exprs = []
        breakpoints = poly.x
        coefficients = poly.c.T

        for i in range(len(breakpoints) - 1):
            xi = round(breakpoints[i], 3)
            xi_next = round(breakpoints[i + 1], 3)
            c3, c2, c1, c0 = (round(v, 4) for v in coefficients[i])

            terms = []
            for expo, coef in enumerate([c3, c2, c1]):
                if abs(coef) > 1e-6:  # 过滤微小系数
                    power = 3 - expo
                    exponent = f"^{power}" if power != 1 else ""
                    base = f"{coef}(t - {xi}){exponent}" if xi != 0 else f"{coef}t{exponent}"
                    term = base.replace("-", " - ").replace("+ -", "- ")
                    terms.append(term)

            if abs(c0) > 1e-6 or not terms:
                c0_str = f"{c0}".replace("-", " - ")
                terms.append(c0_str.lstrip("+"))

            expr = " + ".join(terms).replace("+  -", "- ")
            case_exprs.append(f"{expr}  &\\text{{, }} {xi} \\leq t < {xi_next} \\\\")

        return poly, "\\begin{cases}\n" + "\n".join(case_exprs) + "\n\\end{cases}"

    @staticmethod
    def generate_cubic_spline_latex(x_vals, y_vals):
        """
        生成三次样条表达式
        """
        poly = CubicSpline(x_vals, y_vals)

        case_exprs = []

        for i in range(len(poly.x) - 1):
            xi = round(poly.x[i], 3)
            xi_next = round(poly.x[i + 1], 3)
            c3, c2, c1, c0 = (round(v, 4) for v in poly.c[:, i])

            terms = []
            if c3 != 0:
                base = f"{c3}(t - {xi})^3" if xi != 0 else f"{c3}t^3"
                term = base.replace("-", " - ").replace("  -", " -")
                terms.append(term)
            if c2 != 0:
                base = f"{c2}(t - {xi})^2" if xi != 0 else f"{c2}t^2"
                term = base.replace("-", " - ").replace("  -", " -")
                terms.append(term)
            if c1 != 0:
                base = f"{c1}(t - {xi})" if xi != 0 else f"{c1}t"
                term = base.replace("-", " - ").replace("  -", " -")
                terms.append(term)
            if c0 != 0 or not terms:
                terms.append(f"{c0}")

            expr = " + ".join(terms).replace("+ -", "- ")

            case_exprs.append(f"{expr} &\\text{{, }} {xi} \\leq t < {xi_next} \\\\")

        return poly, "\\begin{cases}\n" + "\n".join(case_exprs) + "\n\\end{cases}"

    def run(self):
        if len(self.points) <= 2:
            self.result.emit(None, "", "")
            return

        try:
            x_vals, y_vals = zip(*self.points)
            if self.method == Interpolation.Akima:
                poly, poly_latex = self.generate_akima_latex(x_vals, y_vals)
            elif self.method == Interpolation.CubicSpline:
                poly, poly_latex = self.generate_cubic_spline_latex(x_vals, y_vals)
            else:
                raise ValueError("不支持的插值方法！")

            self.result.emit(poly, poly_latex, f"{InterpolationManager.get_name(self.method)}插值方法计算完成！")

        except Exception as e:
            self.result.emit(None, "", f"插值多项式计算过程中出错：{e}")


class ConnectionTask(QObject):
    connect_result = Signal(ModbusTcpClient)

    def __init__(self, host: str, port: int):
        super().__init__()
        self.host = host
        self.port = port

    def run(self):
        client = ModbusTcpClient(host=self.host, port=self.port)
        if client.connect() and client.is_socket_open():
            self.connect_result.emit(client)
        else:
            self.connect_result.emit(None)


class SaveRecordTask(QObject):
    status_message = Signal(str)

    def __init__(self, record_data: List[float]):
        super().__init__()
        self.record_data = record_data.copy()

    def run(self):
        try:
            df = pd.DataFrame(self.record_data, columns=["Position"])
            df.to_csv("output.csv", index=False, float_format="%.4f")
            self.status_message.emit(f"保存录制数据成功！")
        except Exception as e:
            self.status_message.emit(f"保存录制数据时发生错误：{e}")


class SaveMockwaveformTask(QObject):
    status_message = Signal(str)

    def __init__(self, path: str, motor_pool: dict, config: dict, y_max: float, y_min: float, points: np.ndarray):
        super().__init__()
        self.path = path
        self.motor_pool = motor_pool.copy()
        self.config = config.copy()
        self.y_max = y_max
        self.y_min = y_min
        self.points = points.copy()

    def run(self):
        try:
            output_points = np.clip(waveform_mapping(self.config, self.motor_pool, self.points), self.y_min, self.y_max)
            df = pd.DataFrame(output_points, columns=["x", "y"])
            df.astype({"x": "float32", "y": "float32"}).to_csv(self.path, index=False, float_format="%.4f")
            self.status_message.emit(f"保存虚拟波形到 {QDir.toNativeSeparators(self.path)}！")
        except Exception as e:
            self.status_message.emit(f"保存虚拟波形时发生错误：{e}")


class SaveWaveformConfigTask(QObject):
    status_message = Signal(str)

    def __init__(self, path: str, config: dict):
        super().__init__()
        self.path = path
        self.config = config.copy()

    def run(self):
        try:
            with open(QDir.toNativeSeparators(self.path), "wb") as f:
                pickle.dump(self.config, f)
            self.status_message.emit(f"保存波形数据到 {QDir.toNativeSeparators(self.path)} ！")
        except Exception as e:
            self.status_message.emit(f"保存波形数据时出错: {e}")


class ReadWaveformConfigTask(QObject):
    status_message = Signal(str)
    result = Signal(dict, str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            with open(QDir.toNativeSeparators(self.path), "rb") as f:
                config = pickle.load(f)
            self.result.emit(config, self.path)
        except Exception as e:
            self.status_message.emit(f"读取波形数据时出错: {e}")
