import re
import time
from threading import Thread
from typing import Dict, Any, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import QThreadPool, Slot, Signal
from PySide6.QtGui import Qt, QPainter, QPen, QColor, QPainterPath, QBrush, QPixmap, QFont, QMouseEvent
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget, QVBoxLayout, QDialog, QGridLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from pymodbus.client import ModbusTcpClient
from scipy.interpolate import lagrange, CubicSpline

from task import ExpressionTask, TaskRunner


class WaveformArea(QWidget):
    points_changed = Signal()
    rule_check_result = Signal(bool)

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config  # 用户配置
        self.interpolated_points = []  # 插值曲线点坐标
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

    def remove_point(self):
        """
        用户移除插值点功能实现
        """
        if len(self.config["插值点集"]) > 2:
            self.config["插值点集"].pop()

    def _interpolate(self, num_points: int=200):
        """
        插值计算功能实现
        :param num_points: 绘制插值曲线点的数量，默认为200
        :return: list(zip(x_new, y_new))，每个元素代表一个插值点
        """
        assert len(self.config["插值点集"]) >= 2, "插值点不满足小于2个！"

        method = self.config.get("插值方法")

        # 拉格朗日插值
        if method == "Lagrange":
            x_vals, y_vals = zip(*self.config["插值点集"])
            poly = lagrange(x_vals, y_vals)
            x_new = np.linspace(min(x_vals), max(x_vals), num_points)
            y_new = poly(x_new)

        # 三次样条插值
        elif method == "Cubic Spline":
            sorted_points = sorted(self.config["插值点集"], key=lambda p: p[0])
            x_vals, y_vals = zip(*sorted_points)
            poly = CubicSpline(x_vals, y_vals)
            x_new = np.linspace(min(x_vals), max(x_vals), num_points)
            y_new = poly(x_new)

        # 未知插值方法
        else:
            raise NotImplementedError("使用未定义的插值方法拟合曲线！")

        self.interpolated_points = list(zip(x_new, y_new))
        if self.dragging_point is None:
            self._rule_check()

    def _rule_check(self):
        """
        规则检查功能实现
        """
        if any(py > 1.0001 or py < -0.0001 for _, py in self.interpolated_points):
            self.rule_check_result.emit(False)
        else:
            self.rule_check_result.emit(True)

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
            # 跳过定点的绘制
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
        if len(self.config["插值点集"]) > 1:
            # 计算插值曲线点集
            self._interpolate()

            if self.interpolated_points:
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

        painter.end()

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
                    self.points_changed.emit()

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
                        self.points_changed.emit()

                # 更新控件显示
                self.update()

        # 右键
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self.config["插值点集"]) > 2:
                self.remove_point()
                self.update()
                self.points_changed.emit()

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


class FormulasDisplay(QWidget):
    status_message = Signal(str)
    thread_pool = QThreadPool().globalInstance()

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config
        self.html_content_forward = r'''
            <!DOCTYPE html>
            <html lang="en">
                <head>
                    <script id="MathJax-script" async src="http://localhost:5000/MathJax/es5/tex-mml-chtml.js"></script>
                    <style>
                        p {
                            text-align:center;
                        }
                    </style>
                </head>
                <body>
                    <p>
        '''
        self.html_content_backward = r'''
                    </p>
                </body>
            </html>
        '''

        layout = QVBoxLayout()

        # 浏览器
        self.webview = QWebEngineView()
        self.webview.setHtml(self.html_content_forward + self.html_content_backward)
        layout.addWidget(self.webview)

        self.setLayout(layout)

    @Slot(list)
    def create_polynomial_task(self, points: Sequence[Tuple[float, float]]):
        """
        新建多项式计算任务功能实现
        :param points: 插值点集
        """
        task = ExpressionTask(points, self.config.get("偏移量"), self.config.get("赋值"), self.config.get("插值方法"))
        task.result_ready.connect(self._on_polynomial_result_ready)
        self.thread_pool.start(TaskRunner(task))

    @Slot(tuple)
    def _on_polynomial_result_ready(self, result: Tuple[str, str]):
        """
        插值多项式计算结果显示功能实现
        :param result: 多项式计算结果，格式为[插值方法，插值多项式]
        """
        if result is None:
            self.status_message.emit("插值计算失败：使用了无效的插值方法！")
            return

        html_context = self.html_content_forward + result[1] + self.html_content_backward
        self.webview.setHtml(html_context)

        self.status_message.emit(f"{result[0]}插值方法计算完成！")


class SettingDialog(QDialog):
    status_message = Signal(str)

    def __init__(self, client: Optional[ModbusTcpClient]):
        super().__init__()
        self.client = client
        self.connect_plc_task = None

        self.setWindowTitle("设置")

        layout = QGridLayout()

        status_label = QLabel("连接状态：")
        status_label.setFixedWidth(60)
        layout.addWidget(status_label, 0, 0)

        self.status_light = QLabel()
        self.status_light.setFixedSize(20, 20)
        layout.addWidget(self.status_light, 0, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        host_label = QLabel("IP地址：")
        host_label.setFixedWidth(60)
        layout.addWidget(host_label, 1, 0)

        self.host = QLineEdit("172.168.0.3")
        self.host.setFixedWidth(110)
        layout.addWidget(self.host, 1, 1)

        port_label = QLabel("端口：")
        port_label.setFixedWidth(60)
        layout.addWidget(port_label, 2, 0)

        self.port = QLineEdit("502")
        self.port.setFixedWidth(110)
        layout.addWidget(self.port, 2, 1)

        self.communication_button = QPushButton()
        self.communication_map = {
            "连接": self._connect_plc,
            "断开": self._disconnect_plc,
        }
        self.communication_button.clicked.connect(lambda: self.communication_map[self.communication_button.text()]())
        layout.addWidget(self.communication_button, 3, 0, 1, 2)

        self._update_connect_status()

        self.setLayout(layout)

    @Slot()
    def _connect_plc(self):
        """
        连接PLC功能实现
        """
        # IPv4规则检查
        host_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        if not bool(re.match(host_pattern, self.host.text())):
            QMessageBox.warning(self, "警告", "请检查当前设置IP地址是否有效！")
            return

        # 端口规则检查
        port_pattern = r'^([0-9]|[1-9][0-9]{1,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$'
        if not bool(re.match(port_pattern, self.port.text())):
            QMessageBox.warning(self, "警告", "请检查当前设置端口是否有效！")
            return

        host = self.host.text()
        port = int(self.port.text())
        self.status_message.emit(f"正在连接PLC（{host}:{port}），请等待！")

        # 分离线程创建ModbusTcpClient，避免连接超时阻塞主线程
        if self.connect_plc_task is None or not self.connect_plc_task.is_alive():
            self.connect_plc_task = Thread(target=self._create_client, args=(host, port))
            self.connect_plc_task.daemon = True
            self.connect_plc_task.start()
        else:
            QMessageBox.warning(self, "警告", "正在连接中，请耐心等待！")

    def _create_client(self, host: str, port: int):
        """
        新建ModbusTcpClient功能实现
        :param host: PLC的连接IP地址
        :param port: PLC的连接端口
        """
        self.status_light.setStyleSheet("background-color: orange; border-radius: 10px;")
        self.client = ModbusTcpClient(host=host, port=port)
        self._update_connect_status("PLC连接成功！", "PLC连接失败！")

    @Slot()
    def _disconnect_plc(self):
        """
        断开PLC连接功能实现
        """
        self.client.close()
        self.status_message.emit("正在断开PLC！")
        while self.client.connect():
            time.sleep(0.1)
        self.client = None
        self._update_connect_status()
        self.status_message.emit("PLC已断开！")

    def _update_connect_status(self, text0: Optional[str]=None, text1: Optional[str]=None):
        """
        更新状态灯状态功能实现
        :param text0: 已连接状态下发送的状态栏信号文本
        :param text1: 未连接状态下发送的状态栏信号文本
        """
        if self.client is not None and self.client.connect():
            self.status_light.setStyleSheet("background-color: green; border-radius: 10px;")
            self.communication_button.setText("断开")
            if text0 is not None:
                self.status_message.emit(text0)
        else:
            self.status_light.setStyleSheet("background-color: red; border-radius: 10px;")
            self.communication_button.setText("连接")
            if text1 is not None:
                self.status_message.emit(text1)