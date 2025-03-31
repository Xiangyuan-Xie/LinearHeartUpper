from typing import Sequence, Tuple, Any

from PySide6.QtCore import QRunnable, QObject, Signal
from scipy.interpolate import CubicSpline, Akima1DInterpolator

from common import Interpolation, InterpolationManager


class TaskRunner(QRunnable):
    def __init__(self, task):
        super().__init__()
        self.task = task

    def run(self):
        self.task.run()  # 调用任务类的 run 方法


class ExpressionTask(QObject):
    result = Signal(Any, str, str)

    def __init__(self, points: Sequence[Tuple[float, float]],
                 offset: float, amplitude: float, method: Interpolation):
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
                    base = (
                        f"{coef}(t - {xi}){exponent}"
                        if xi != 0
                        else f"{coef}t{exponent}"
                    )
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
