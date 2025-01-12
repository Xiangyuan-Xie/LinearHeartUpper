from PySide6.QtCore import QRunnable, QObject, Signal
from scipy.interpolate import lagrange, CubicSpline
from sympy import latex, symbols, simplify


class ExpressionWorker(QObject):
    result_ready = Signal(tuple)


class ExpressionTask(QRunnable):
    def __init__(self, points, method, worker):
        super().__init__()
        self.points = points
        self.method = method
        self.worker = worker

    def run(self):
        """
        插值多项式计算功能实现
        """
        if len(self.points) < 2:
            self.worker.result_ready.emit(None)
            return

        # 拉格朗日插值
        if self.method == "Lagrange":
            # 插值计算
            x_vals, y_vals = zip(*self.points)
            poly = lagrange(x_vals, y_vals)

            # 将插值多项式转换为 sympy 表达式
            x = symbols('t')
            poly_expr = sum(round(c, 4) * x ** i for i, c in enumerate(poly))

            # 转换为 LaTeX 表达式
            simplified_poly = simplify(poly_expr)
            poly_latex = latex(simplified_poly)
            poly_latex = "\( " + poly_latex + " \)"

        # 三次样条插值
        elif self.method == "Cubic Spline":
            sorted_points = sorted(self.points, key=lambda p: p[0])
            x_vals, y_vals = zip(*sorted_points)

            # 只有2个点，使用直线插值
            if len(self.points) == 2:
                x1, y1 = sorted_points[0]
                x2, y2 = sorted_points[1]

                # 构造直线方程 y = kx + b
                x = symbols('t')
                k = round((y2 - y1) / (x2 - x1), 4)
                b = round(y1 - k * x1, 4)
                poly_expr = k * x + b
                simplified_poly = simplify(poly_expr)
                poly_latex = latex(simplified_poly)

            # 有至少3个点
            else:
                # 使用三次样条插值
                cs = CubicSpline(x_vals, y_vals)
                x = symbols('t')
                poly_expr = []
                for i in range(len(cs.x) - 1):
                    # 获取每段多项式的系数
                    c3, c2, c1, c0 = cs.c[:, i]
                    c3, c2, c1, c0 = map(lambda c: round(c, 4), (c3, c2, c1, c0))  # 四舍五入到4位小数
                    interval = "[{:.3f}, {:.3f}]".format(cs.x[i], cs.x[i + 1])  # 使用 str.format()
                    poly = (
                            c3 * (x - cs.x[i]) ** 3 +
                            c2 * (x - cs.x[i]) ** 2 +
                            c1 * (x - cs.x[i]) +
                            c0
                    )
                    simplified_poly = simplify(poly)
                    poly_expr.append(
                        latex(simplified_poly) + "\\text{,} \\ x \\in " + interval + " \\\\"
                    )
                poly_latex = "\\begin{cases}\n" + " \\\n".join(poly_expr) + "\n\\end{cases}"

        # 未知插值方法
        else:
            self.worker.result_ready.emit(None)
            return

        print(poly_latex)

        # 发射结果信号
        self.worker.result_ready.emit((self.method, poly_latex))
