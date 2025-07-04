from collections import deque
from typing import List, Sequence

import numpy as np
from loguru import logger
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QMargins, QPointF, Qt, QThreadPool, QTimer, Signal, Slot

from linearheart.common.common import compute_features, waveform_mapping
from linearheart.utils.task import SaveRecordTask, TaskRunner


class FeedbackWaveformChart(QChartView):
    status_message = Signal()
    thread_pool = QThreadPool.globalInstance()
    MAX_STORAGE = 1000  # 数据存储上限
    MIN_DISPLAY = 10  # 最小显示点数
    MAX_DISPLAY = 1000  # 最大显示点数

    def __init__(self, y_range: Sequence[float], display_window=100):
        super().__init__()
        self.data_pool: deque[float] = deque(maxlen=self.MAX_STORAGE)

        self.record_status = False
        self.record_data: List[float] = []

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
        self.adjust_y_scale(y_range[0], y_range[1])
        self.chart.addAxis(self.y_axis, Qt.AlignmentFlag.AlignLeft)
        self.waveform_series.attachAxis(self.y_axis)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(100)
        self.refresh_timer.timeout.connect(self._refresh_visualization)
        self.refresh_timer.start()

    def add_points(self, points: Sequence[float]) -> None:
        """
        向数据池中增加新数据点并触发更新
        :param points: 新数据点
        """
        if not points:
            return

        clean_points = [p for p in points if np.isfinite(p)]
        if not clean_points:
            return

        self.data_pool.extend(clean_points)
        if self.record_status:
            self.record_data.extend(clean_points)

    def adjust_display_scope(self, new_scope: int):
        """
        调节显示窗口
        :param new_scope: 新显示范围
        """
        if self._display_range != new_scope:
            self._display_range = new_scope
            self._refresh_visualization(force_redraw=True)

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

    def adjust_y_scale(self, y_min: float, y_max: float):
        """
        坐标Y轴自适应(动态边距)
        :param y_min: 位置最小值
        :param y_max: 位置最大值
        """
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
        self.adjust_y_scale(y_range[0], y_range[1])  # Y轴范围
        self.axis_y.setTickCount(9)  # Y轴刻度线数量
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.waveform_series.attachAxis(self.axis_y)

    def update_data(self, new_samples: np.ndarray):
        mapping_points = np.clip(
            waveform_mapping(self.config, self.motor_pool, new_samples), self.axis_y.min(), self.axis_y.max()
        )

        vel, acc, jerk = compute_features(mapping_points)
        logger.debug(
            f"虚拟波形拟合完毕：\n"
            f"最大值：{max(mapping_points[:, 1])}\n"
            f"最小值：{min(mapping_points[:, 1])}\n"
            f"最大速度：{vel}\n"
            f"最大加速度：{acc}\n"
            f"最大加加速度：{jerk}"
        )

        tiled_points = []
        repeat_count = int(np.ceil(self.axis_x.max() * self.config["频率"]))
        period = 1 / self.config["频率"]
        for i in range(repeat_count):
            for point in mapping_points:
                x = point[0]
                if x <= self.axis_x.max():
                    tiled_points.append(QPointF(i * period + point[0], point[1]))
                else:
                    break

        self.waveform_series.replace(tiled_points)
        self.chart.update()

    def adjust_y_scale(self, y_min: float, y_max: float):
        """
        坐标Y轴自适应(动态边距)
        :param y_min: 位置最小值
        :param y_max: 位置最大值
        """
        data_span = y_max - y_min
        if data_span == 0:  # 处理零波动场景
            padding = max(abs(y_min) * 0.2, 0.1)
        else:
            padding = data_span * 0.15  # 基础边距15%
            padding = max(padding, data_span * 0.05)  # 最小边距5%

        self.axis_y.setRange(y_min - padding, y_max + padding)
