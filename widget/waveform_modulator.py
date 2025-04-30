import enum
from typing import Sequence, Tuple

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtGui import Qt, QPainter, QPen, QColor, QPainterPath, QBrush, QPixmap, QFont, QMouseEvent
from PySide6.QtWidgets import QWidget

from common import Interpolation, InterpolationManager


class WaveformStatus(enum.Enum):
    Unset = 0
    Normal = 1
    Abnormal = 2


class WaveformModulator(QWidget):
    points_changed = Signal()
    waveform_status = Signal(WaveformStatus)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config  # 用户配置
        self.interpolated_points = np.zeros((1001, 2), dtype=np.float32)  # 曲线点集
        self.x_range = 1.0  # X轴范围
        self.y_range = 1.0  # Y轴范围
        self.static_pixmap = None  # 缓存静态内容
        self.dragging_point = None  # 当前拖动点的索引
        self.setMouseTracking(True)  # 启用鼠标跟踪，捕捉鼠标移动事件

    def add_point(self, x: float, y: float):
        """
        用户添加插值点功能实现
        :param x: 插值点X坐标
        :param y: 插值点Y坐标
        """
        self.config["插值点集"].append((x, y))
        self.calc_polynomial()

    def remove_point(self):
        """
        用户移除插值点功能实现
        """
        if len(self.config["插值点集"]) <= 2:
            return

        self.config["插值点集"].pop()
        self.calc_polynomial()

    def calc_polynomial(self):
        """
        启动多项式计算任务
        """
        self.points_changed.emit()

    def paintEvent(self, event):
        """
        插值点和插值曲线绘制功能实现
        """
        # 如果静态内容没有缓存，则进行缓存
        if self.static_pixmap is None or self.static_pixmap.size() != self.size():
            self._update_static_cache()

        # 画笔初始化
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制缓存的静态内容
        painter.drawPixmap(0, 0, self.static_pixmap)

        # 绘制数据点
        for index, point in enumerate(self.config["插值点集"]):
            # 跳过初始点的绘制
            if index < 2:
                continue

            # 计算坐标的比例，将其转换到屏幕像素坐标系
            x = 50 + (point[0] / self.x_range) * (self.width() - 100)
            y = self.height() - 50 - (point[1] / self.y_range) * (self.height() - 100)

            # 若绘制点为拖动中的点则高亮显示
            if self.dragging_point == index:
                painter.setPen(QPen(QColor(0, 255, 0), 2))  # 绿色
                painter.setBrush(QColor(0, 255, 0))
            else:
                painter.setPen(QPen(QColor(255, 0, 0)))  # 红色
                painter.setBrush(QColor(255, 0, 0))

            square_size = 6  # 点的大小
            painter.drawRect(int(x) - square_size // 2, int(y) - square_size // 2, square_size, square_size)

        # 绘制插值曲线
        if len(self.config["插值点集"]) > 2:
            self.interpolated_points = self.interpolate(self.config["插值方法"], self.config["插值点集"])  # 计算插值曲线点集
            if self.interpolated_points.size > 0:
                painter.setPen(QPen(QColor(0, 0, 255), 2))  # 蓝色

                path = QPainterPath()
                first_point = self.interpolated_points[0]
                x1 = 50 + (first_point[0] / self.x_range) * (self.width() - 100)
                y1 = self.height() - 50 - (first_point[1] / self.y_range) * (self.height() - 100)
                path.moveTo(x1, y1)

                for point in self.interpolated_points[1:]:
                    x2 = 50 + (point[0] / self.x_range) * (self.width() - 100)
                    y2 = self.height() - 50 - (point[1] / self.y_range) * (self.height() - 100)
                    path.lineTo(x2, y2)

                painter.setBrush(QBrush())  # 不填充路径区域
                painter.drawPath(path)

        # 更新波形状态
        self.update_waveform_status()

        painter.end()

    @staticmethod
    def interpolate(method: Interpolation, points: Sequence[Sequence[float]], num_points: int=1001) -> np.ndarray:
        """
        插值计算功能实现
        :param method: 插值方法
        :param points: 插值点集合
        :param num_points: 绘制插值曲线点的数量，默认为1000
        :return: np.ndarray，每个元素代表一个插值点
        """
        assert len(points) > 2, "插值点数量不满足大于2个！"

        sorted_points = sorted(points, key=lambda p: p[0])
        x_vals, y_vals = zip(*sorted_points)
        poly = InterpolationManager.get_class(method)(x_vals, y_vals)
        x_new = np.linspace(min(x_vals), max(x_vals), num_points)
        y_new = poly(x_new)

        return np.column_stack((x_new, y_new))

    def update_waveform_status(self):
        """
        更新波形状态功能实现
        """
        if len(self.config["插值点集"]) <= 2:
            self.waveform_status.emit(WaveformStatus.Unset)
        else:
            if any(py > 1.0001 or py < -0.0001 for _, py in self.interpolated_points):
                self.waveform_status.emit(WaveformStatus.Abnormal)
            else:
                self.waveform_status.emit(WaveformStatus.Normal)

    def _update_static_cache(self):
        """
        更新静态缓存功能实现
        """
        # 获取设备的像素比率
        device_pixel_ratio = self.devicePixelRatioF()

        # 存储静态内容，并根据设备像素比率调整大小
        scaled_size = self.size() * device_pixel_ratio
        self.static_pixmap = QPixmap(scaled_size)
        self.static_pixmap.setDevicePixelRatio(device_pixel_ratio)

        # 填充白色背景，确保不透明
        self.static_pixmap.fill(Qt.GlobalColor.white)

        # 画笔初始化
        static_painter = QPainter(self.static_pixmap)
        static_painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 设置坐标轴的样式（黑色、较粗线条）
        static_painter.setPen(QPen(QColor(0, 0, 0), 2))
        static_painter.drawLine(50, self.height() - 50, self.width() - 50, self.height() - 50)  # X轴
        static_painter.drawLine(50, 50, 50, self.height() - 50)  # Y轴

        # 绘制网格线（浅灰色、虚线）
        grid_pen = QPen(QColor(200, 200, 200), 1, Qt.PenStyle.DotLine)
        static_painter.setPen(grid_pen)
        tick_interval = 30  # 刻度间隔，单位为像素
        for x in range(50 + tick_interval, self.width() - 50, tick_interval):  # 垂直网格线
            static_painter.drawLine(x, 50, x, self.height() - 50)
        for y in range(self.height() - 50 - tick_interval, 50, -tick_interval):  # 水平网格线
            static_painter.drawLine(50, y, self.width() - 50, y)

        # 绘制刻度线
        tick_pen = QPen(QColor(0, 0, 0), 1, Qt.PenStyle.SolidLine)
        static_painter.setPen(tick_pen)
        for x in range(50 + tick_interval, self.width() - 50, tick_interval):  # X轴刻度
            tick_value = (x - 50) / (self.width() - 100) * self.x_range
            static_painter.drawLine(x, self.height() - 50, x, self.height() - 45)
            static_painter.drawText(x - 10, self.height() - 30, f"{tick_value:.2f}")
        for y in range(self.height() - 50 - tick_interval, 50, -tick_interval):  # Y轴刻度
            tick_value = (self.height() - 50 - y) / (self.height() - 100) * self.y_range
            static_painter.drawLine(45, y, 50, y)
            static_painter.drawText(15, y + 5, f"{tick_value:.2f}")

        # 设置坐标轴标题的字体和颜色
        title_font = QFont('Times New Roman', 12, QFont.Weight.Bold)  # 加粗
        static_painter.setFont(title_font)
        title_color = QColor(0, 0, 0)  # 黑色
        static_painter.setPen(QPen(title_color))

        # 绘制坐标轴标题
        static_painter.drawText(25, self.height() - 30, 'O')  # 原点
        static_painter.drawText(self.width() - 65, self.height() - 10, "Period")  # X轴标题
        static_painter.drawText(10, 30, "Amplitude")  # Y轴标题

        static_painter.end()

    def resizeEvent(self, event):
        """
        重写事件方法，窗口尺寸改变后更新静态缓存实现
        """
        self._update_static_cache()

    def mousePressEvent(self, event: QMouseEvent):
        """
        重写事件方法，鼠标左右键功能实现
        """
        # 左键
        if event.button() == Qt.MouseButton.LeftButton:
            # 计算点击位置在控件坐标系的坐标
            x = event.position().x() - 50
            y = self.height() - event.position().y() - 50

            if 0 <= x <= self.width() - 100 and 0 <= y <= self.height() - 100:
                # 若存在正在拖动的点则退出拖动状态
                if self.dragging_point is not None:
                    self.dragging_point = None

                # 不存在正在拖动的点
                else:
                    tolerance = 8  # 容忍范围内视为可拖动，单位为像素
                    for i, (px, py) in enumerate(self.config["插值点集"]):
                        # 跳过定点的检测
                        if i < 2:
                            continue

                        # 将点的坐标从数学坐标系还原到控件坐标系
                        wx = (px / self.x_range) * (self.width() - 100)
                        wy = (py / self.y_range) * (self.height() - 100)

                        # 满足容忍条件则进入拖动状态
                        if abs(x - wx) < tolerance and abs(y - wy) < tolerance:
                            self.dragging_point = i
                            break

                    # 如果点击位置不接近已有点，则新增一个点
                    if self.dragging_point is None:
                        mx = (x / (self.width() - 100)) * self.x_range
                        my = (y / (self.height() - 100)) * self.y_range
                        self.add_point(mx, my)

                # 更新控件显示
                self.update()

        # 右键
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self.config["插值点集"]) > 2:
                self.remove_point()
                self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        """
        重写事件方法，插值点拖动功能实现
        """
        if self.dragging_point is not None:
            # 计算新的点的位置
            x = event.position().x() - 50  # 距离左边的偏移量
            y = self.height() - event.position().y() - 50  # 距离上边的偏移量

            # 将坐标转换为实际坐标系中的点
            if 0 <= x <= self.width() - 100 and 0 <= y <= self.height() - 100:
                scaled_x = (x / (self.width() - 100)) * self.x_range
                scaled_y = (y / (self.height() - 100)) * self.y_range

                # 更新点的位置
                self.config["插值点集"][self.dragging_point] = (scaled_x, scaled_y)
                self.update()
                self.calc_polynomial()
