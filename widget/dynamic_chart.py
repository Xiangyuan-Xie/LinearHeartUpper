from PySide6.QtCharts import QChartView, QLineSeries, QChart, QValueAxis
from PySide6.QtCore import Qt, QPointF, QMargins


class DynamicChart(QChartView):
    def __init__(self, size=100):
        super().__init__()
        self.size = size

        # 初始化数据容器
        self.y_values = [0 for i in range(size)]

        # 创建图表
        self.chart = QChart()
        self.series = QLineSeries()

        # 添加初始数据点
        self.series.replace([
            QPointF(x, y)
            for x, y in enumerate(self.y_values)
        ])

        # 配置图表
        self.setChart(self.chart)
        self.chart.addSeries(self.series)
        self.chart.legend().hide()
        self.chart.setMargins(QMargins(5, 5, 5, 5))  # 设置图表边距

        # 坐标轴
        self.axis_x = QValueAxis()
        self.axis_x.setRange(0, self.size)
        self.axis_y = QValueAxis()
        self.axis_y.setRange(-1, 1)
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.axis_x)
        self.series.attachAxis(self.axis_y)

    def update_data(self, pos):
        """
        动态更新数据
        """
        # 维护队列长度
        if len(self.y_values) >= self.size:
            self.y_values.pop(0)
        self.y_values.append(pos)

        # 更新图表数据
        self.series.replace([
            QPointF(x, y)
            for x, y in enumerate(self.y_values)
        ])

        # 自动调整Y轴
        self._adjust_y_axis()

    def _adjust_y_axis(self):
        """
        Y轴自适应逻辑
        """
        y_min = min(self.y_values)
        y_max = max(self.y_values)

        # 处理数据全等的情况
        if y_min == y_max:
            delta = abs(y_min) * 0.1 if y_min != 0 else 1
            y_min -= delta
            y_max += delta

            # 添加5%边距
        y_padding = (y_max - y_min) * 0.05
        axis_y = self.chart.axes(Qt.Orientation.Vertical)[0]
        axis_y.setRange(y_min - y_padding, y_max + y_padding)
