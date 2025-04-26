from collections import deque
from typing import Sequence, Union

import numpy as np
from PySide6.QtCharts import QChartView, QLineSeries, QChart, QValueAxis
from PySide6.QtCore import Qt, QPointF, QMargins, Slot, QThreadPool, Signal

from task import SaveRecordTask, TaskRunner


class FeedbackWaveformChart(QChartView):
    status_message = Signal()
    thread_pool = QThreadPool.globalInstance()
    MAX_STORAGE = 1000  # 数据存储上限
    MIN_DISPLAY = 10    # 最小显示点数
    MAX_DISPLAY = 1000  # 最大显示点数

    def __init__(self, display_window=100):
        super().__init__()
        self.data_pool = deque(maxlen=self.MAX_STORAGE)

        self.record_status = False
        self.record_data = []

        self._display_range = min(max(display_window, self.MIN_DISPLAY), self.MAX_DISPLAY)

        self.chart = QChart()
        self.setChart(self.chart)
        self.chart.setMargins(QMargins(5, 5, 5, 5))
        self.chart.legend().hide()

        self.waveform_series = QLineSeries()
        self.chart.addSeries(self.waveform_series)

        self.x_axis = QValueAxis()
        self.x_axis.setRange(0, self._display_range)
        self.chart.addAxis(self.x_axis, Qt.AlignmentFlag.AlignBottom)
        self.waveform_series.attachAxis(self.x_axis)

        self.y_axis = QValueAxis()
        self.y_axis.setRange(-2, 22)  # TODO: 之后改成与行程相同
        self.chart.addAxis(self.y_axis, Qt.AlignmentFlag.AlignLeft)
        self.waveform_series.attachAxis(self.y_axis)

    def add_points(self, points: Union[float, Sequence[float]]) -> None:
        """
        向数据池中增加新数据点并触发更新
        :param points: 新数据点
        """
        if not points:
            return

        self.data_pool.extend(points)
        if self.record_status:
            self.record_data.append(points)
        self._refresh_visualization()
        # self._dynamic_scale_adjustment()

    def adjust_display_scope(self, new_scope: int):
        """
        调节显示窗口
        :param new_scope: 新显示范围
        """
        if self._display_range != new_scope:
            self._display_range = new_scope
            self._refresh_visualization(force_redraw=True)
            # self._dynamic_scale_adjustment()

    def _refresh_visualization(self, force_redraw=False):
        """
        波形渲染引擎
        """
        # 获取有效数据段
        valid_samples = min(len(self.data_pool), self._display_range)
        display_data = list(self.data_pool)[-valid_samples:]

        # 坐标点生成
        plot_points = [QPointF(x, y) for x, y in enumerate(display_data)]

        # 渲染优化：避免重复绘制相同数据
        if force_redraw or plot_points != self.waveform_series.pointsVector():
            self.waveform_series.replace(plot_points)
            self._update_x_axis(valid_samples)
            self.chart.update()

    def _dynamic_scale_adjustment(self):
        """
        坐标轴自适应
        """
        if not self.data_pool:
            return

        # 计算当前显示窗口内的数据特征
        visible_data = list(self.data_pool)[-self._display_range:]
        y_min = min(visible_data)
        y_max = max(visible_data)

        # 动态边距
        data_span = y_max - y_min
        if data_span == 0:  # 处理零波动场景
            padding = max(abs(y_min) * 0.2, 0.1)
        else:
            padding = data_span * 0.15  # 基础边距15%
            padding = max(padding, data_span * 0.05)  # 最小边距5%

        self.y_axis.setRange(y_min - padding, y_max + padding)

    def _update_x_axis(self, valid_samples):
        """
        更新X轴范围
        """
        target_range = max(valid_samples, self._display_range)
        if self.x_axis.max() != target_range:
            self.x_axis.setRange(0, target_range)

    @Slot()
    def toggle_record_status(self, status: bool):
        """
        开始/结束波形录制
        :param status: 新状态
        """
        self.record_status = status
        if not self.record_status:
            task = SaveRecordTask(self.record_data)
            task.status_message.connect(self.status_message.emit)
            self.thread_pool.start(TaskRunner(task))
            self.record_data.clear()


class MockWaveformChart(QChartView):
    def __init__(self, config: dict, motor_pool, y_range: Sequence[float]):
        super().__init__()
        self.config = config
        self.motor_pool = motor_pool
        self.points = None

        self.chart = QChart()
        self.setChart(self.chart)
        self.chart.setMargins(QMargins(5, 5, 5, 5))
        self.chart.legend().hide()

        self.waveform_series = QLineSeries()
        self.chart.addSeries(self.waveform_series)

        self.axis_x = QValueAxis()
        self.axis_x.setRange(0, 1)  # X轴范围
        self.axis_x.setTickCount(24)  # X轴刻度线数量
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.waveform_series.attachAxis(self.axis_x)

        self.axis_y = QValueAxis()
        self.axis_y.setRange(y_range[0], y_range[1])  # Y轴范围
        self.axis_y.setTickCount(9)  # Y轴刻度线数量
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.waveform_series.attachAxis(self.axis_y)

    def update_data(self, new_samples: Sequence[Sequence[float]]):
        if not new_samples:
            return

        # 参数提取
        motor = self.motor_pool[self.config["当前电机"]]
        zero_pos, limit_pos = motor["零位"], motor["限位"]
        freq, scale, offset = self.config["频率"], self.config["幅值比例"], self.config["偏移量"]

        # 向量化初始处理
        matrix = np.array(new_samples, dtype=np.float32)
        matrix[:, 0] /= freq
        matrix[:, 1] = (matrix[:, 1] * (limit_pos - zero_pos) - zero_pos) * scale + offset

        # 时间维度展开
        period = int(self.axis_x.max() * freq)
        deltas = np.arange(1, period + 1) / freq
        time_cube = matrix[:, 0][np.newaxis, :] + deltas[:, np.newaxis]
        expanded_time = time_cube.reshape(-1, 1)
        expanded_value = np.tile(matrix[:, 1], period).reshape(-1, 1)

        # 预分配内存合并
        total_rows = matrix.shape[0] * (period + 1)
        prealloc = np.empty((total_rows, 2), dtype=np.float32)
        prealloc[:matrix.shape[0]] = matrix
        prealloc[matrix.shape[0]:] = np.hstack([expanded_time, expanded_value])

        # 边界裁剪优化
        mask = (prealloc[:, 0] >= self.axis_x.min()) & (prealloc[:, 0] <= self.axis_x.max())
        clipped = prealloc[mask]

        # 数据更新
        self.waveform_series.replace([
            QPointF(x, np.clip(y, self.axis_y.min(), self.axis_y.max()))
            for x, y in clipped[:, :2]
        ])
        self.chart.update()