from typing import Sequence, Tuple

from PySide6.QtCore import QRunnable, QObject, Signal
from scipy.interpolate import lagrange, CubicSpline


class TaskRunner(QRunnable):
    def __init__(self, task):
        super().__init__()
        self.task = task

    def run(self):
        self.task.run()  # 调用任务类的 run 方法


class ExpressionTask(QObject):
    result_ready = Signal(tuple)

    def __init__(self, points: Sequence[Tuple[float, float]],
                 offset: float, amplitude: float, method: str):
        super().__init__()
        self.__slots__ = ('points', 'offset', 'amplitude', 'method')
        self.points = sorted(points, key=lambda p: p[0]) if method == "Cubic Spline" else points
        self.offset = offset
        self.amplitude = amplitude
        self.method = method

    @staticmethod
    def _generate_lagrange_latex(x_vals, y_vals):
        """
        生成拉格朗日插值多项式
        """
        poly = lagrange(x_vals, y_vals)
        coeffs = poly.coeffs.tolist()

        # 生成多项式项列表
        terms = []
        for i, c in enumerate(coeffs):
            power = len(coeffs) - 1 - i
            rc = round(c, 4)
            if rc == 0 and len(coeffs) > 1: continue

            if power == 0:
                terms.append(f"{rc}")
            elif power == 1:
                terms.append(f"{rc}t")
            else:
                terms.append(f"{rc}t^{power}")

        expr = " + ".join(terms).replace("+ -", " - ")
        return f"\\( {expr} \\)"

    @staticmethod
    def _generate_cubic_spline_latex(x_vals, y_vals):
        """
        生成三次样条表达式
        """
        cs = CubicSpline(x_vals, y_vals)
        case_exprs = []

        for i in range(len(cs.x) - 1):
            xi = round(cs.x[i], 3)
            xi_next = round(cs.x[i + 1], 3)
            c3, c2, c1, c0 = (round(v, 4) for v in cs.c[:, i])

            # 处理负号显示问题
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

            # 使用对齐语法替代 cases
            case_exprs.append(
                f"{expr} &\\text{{, }} {xi} \\leq t < {xi_next} \\\\"
            )

        return "\\begin{cases}\n" + "\n".join(case_exprs) + "\n\\end{cases}"

    def run(self):
        assert len(self.points) >= 2, "插值点不满足小于2个！"

        try:
            if self.method == "Lagrange":
                x_vals, y_vals = zip(*self.points)
                poly_latex = self._generate_lagrange_latex(x_vals, y_vals)

            elif self.method == "Cubic Spline":
                x_vals, y_vals = zip(*self.points)
                if len(x_vals) == 2:  # 直线特例
                    k = round((y_vals[1] - y_vals[0]) / (x_vals[1] - x_vals[0]), 4)
                    b = round(y_vals[0] - k * x_vals[0], 4)
                    poly_latex = f"\\( {k}t + {b} \\)"
                else:
                    poly_latex = self._generate_cubic_spline_latex(x_vals, y_vals)

            else:
                raise ValueError("试图使用未定义的插值类型")

            self.result_ready.emit((self.method, poly_latex))

        except Exception as e:
            self.result_ready.emit(("ERROR", str(e)))
