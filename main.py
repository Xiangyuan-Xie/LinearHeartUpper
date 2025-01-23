import math
import pickle
import re
import sys
import time
from datetime import datetime
from threading import Thread
from typing import Optional, Dict, Any

import numpy as np
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt, QThreadPool, Slot, QPointF
from PySide6.QtGui import QPainter, QPen, QMouseEvent, QColor, QFont, QPainterPath, QPixmap, QBrush, QAction
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QMainWindow, QHBoxLayout, QComboBox, \
    QLabel, QFrame, QGridLayout, QDoubleSpinBox, QPushButton, QTabWidget, QMessageBox, QMenuBar, QMenu, QFileDialog, \
    QDialog, QLineEdit, QSpinBox
from flask import Flask
from flask_cors import CORS
from pymodbus.client import ModbusTcpClient

from multi_thread import *


class WaveformArea(QWidget):
    points_changed = Signal()
    validity_check_result = Signal(bool)

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

    def interpolate(self, num_points: int=200):
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
            self.validity_check()

    def validity_check(self):
        """
        有效性检查功能实现
        """
        if any(py > 1.0001 or py < -0.0001 for _, py in self.interpolated_points):
            self.validity_check_result.emit(False)
        else:
            self.validity_check_result.emit(True)

    def paintEvent(self, event):
        """
        插值点和插值曲线绘制功能实现
        """
        # 如果静态内容没有缓存，则进行缓存
        if self.static_pixmap is None or self.static_pixmap.size() != self.size():
            self.update_static_pixmap()

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
            self.interpolate()

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

    def update_static_pixmap(self):
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
        self.update_static_pixmap()

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

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config
        self.thread_pool = QThreadPool.globalInstance()
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
    def update_polynomial(self, points: Sequence[tuple[float, float]]):
        """
        插值多项式计算任务加载功能实现
        :param points: 插值点集
        """
        worker = ExpressionWorker()
        worker.result_ready.connect(self.on_result_ready)
        task = ExpressionTask(points,
                              self.config.get("偏移量"),
                              self.config.get("赋值"),
                              self.config.get("插值方法"),
                              worker)
        self.thread_pool.start(task)

    @Slot(tuple)
    def on_result_ready(self, result: Optional[str]):
        """
        插值多项式计算结果显示功能实现
        :param result:
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
            "连接": self.connect_plc,
            "断开": self.disconnect_plc,
        }
        self.communication_button.clicked.connect(lambda: self.communication_map[self.communication_button.text()]())
        layout.addWidget(self.communication_button, 3, 0, 1, 2)

        self.update_connect_status()

        self.setLayout(layout)

    @Slot()
    def connect_plc(self):
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
            self.connect_plc_task = Thread(target=self.create_client, args=(host, port))
            self.connect_plc_task.daemon = True
            self.connect_plc_task.start()
        else:
            QMessageBox.warning(self, "警告", "正在连接中，请耐心等待！")

    def create_client(self, host: str, port: int):
        """
        新建ModbusTcpClient功能实现
        :param host: PLC的连接IP地址
        :param port: PLC的连接端口
        """
        self.status_light.setStyleSheet("background-color: orange; border-radius: 10px;")
        self.client = ModbusTcpClient(host=host, port=port)
        self.update_connect_status("PLC连接成功！", "PLC连接失败！")

    @Slot()
    def disconnect_plc(self):
        """
        断开PLC连接功能实现
        """
        self.client.close()
        self.status_message.emit("正在断开PLC！")
        while self.client.connect():
            time.sleep(0.1)
        self.client = None
        self.update_connect_status()
        self.status_message.emit("PLC已断开！")

    def update_connect_status(self, text0: Optional[str]=None, text1: Optional[str]=None):
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = {
            "插值方法": "Lagrange",
            "插值点集": [(0.0, 0.0), (1.0, 0.0)],
            "偏移量": 0.0,
            "频率": 1.0,
            "幅值比例": 100,
            "有效性检查结果": True,
        }
        self.motor_pool = {
            "1号电机": {
                "导轨长度": 100.0,
            }
        }
        self.client = None

        # MathJax服务器
        server = Flask(__name__, static_folder="./MathJax")
        CORS(server)  # 允许跨域请求
        mathjax_thread = Thread(target=lambda: server.run(host='0.0.0.0', port=5000, threaded=True))
        mathjax_thread.daemon = True
        mathjax_thread.start()

        # 设置窗口标题
        self.setWindowTitle("直线电机心脏驱动系统PC端 V4.1.1")
        self.setGeometry(100, 100, 1280, 720)

        # 布局
        main_layout = QVBoxLayout()
        upper_layout = QHBoxLayout()
        lower_layout = QHBoxLayout()

        # 中心部件
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # 状态栏
        self.status_bar = self.statusBar()

        """
        菜单栏
        """
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        # 文件
        file_menu = QMenu("文件", self)
        menu_bar.addMenu(file_menu)

        read_waveform_action = QAction("读取波形", self)
        read_waveform_action.triggered.connect(self.read_waveform)
        file_menu.addAction(read_waveform_action)

        save_waveform_action = QAction("保存波形", self)
        save_waveform_action.triggered.connect(self.save_waveform)
        file_menu.addAction(save_waveform_action)

        # 设置
        setting_action = QAction("设置", self)
        setting_action.triggered.connect(self.open_dialog)
        menu_bar.addAction(setting_action)

        """
        上区域 - 左布局
        """
        left_layout = QVBoxLayout()

        # 波形图区域
        self.waveform_area = WaveformArea(self.config)
        self.waveform_area.points_changed.connect(lambda: (
            self.formulas_area.update_polynomial(self.config["插值点集"]),
            self.update_status(f"正在使用{self.config.get('插值方法')}进行计算！"),
        ))
        self.waveform_area.validity_check_result.connect(lambda result: (
            self.config.__setitem__("有效性检查结果", result),
            self.update_validity_display(result),
            self.update_mock_waveform(),
        ))
        left_layout.addWidget(self.waveform_area)

        # 有效性检测区域
        self.validity_display_area = QLabel()
        self.validity_display_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_validity_display(self.config.get("有效性检查结果"))
        left_layout.addWidget(self.validity_display_area)

        # 左布局缩放因子
        left_layout.setStretch(0, 9)
        left_layout.setStretch(1, 1)

        """
        上区域 - 中布局
        """
        middle_layout = QVBoxLayout()

        # 电机选择
        motor_setting_frame = QFrame()
        motor_setting_frame.setFrameShape(QFrame.Shape.StyledPanel)
        motor_setting_frame.setFrameShadow(QFrame.Shadow.Raised)
        motor_setting_layout = QGridLayout()  # 使用垂直布局

        motor_setting_label = QLabel("<h3>电机设置</h3>")
        motor_setting_layout.addWidget(motor_setting_label, 0, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter)

        select_motor_label = QLabel("选择电机：")
        select_motor_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_setting_layout.addWidget(select_motor_label, 1, 0, alignment=Qt.AlignmentFlag.AlignCenter)

        self.motor_selection = QComboBox()
        self.motor_selection.addItems([motor for motor, _ in self.motor_pool.items()])
        motor_setting_layout.addWidget(self.motor_selection, 1, 1)

        rail_length_label = QLabel("导轨长度：")
        rail_length_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_setting_layout.addWidget(rail_length_label, 2, 0, alignment=Qt.AlignmentFlag.AlignCenter)

        self.rail_length = QDoubleSpinBox()
        self.rail_length.setRange(0, 1000)
        self.rail_length.setDecimals(1)
        self.rail_length.setSingleStep(0.1)
        self.rail_length.setValue(100)
        self.rail_length.setSuffix(" mm")
        self.rail_length.valueChanged.connect(lambda: (
            self.motor_pool.get(self.motor_selection.currentText()).__setitem__("导轨长度", self.rail_length.value()),
            self.set_offset.setMaximum(self.rail_length.value()),
            self.mock_axis_y.setRange(0, self.rail_length.value()),
        ))
        motor_setting_layout.addWidget(self.rail_length, 2, 1)

        motor_setting_frame.setLayout(motor_setting_layout)
        middle_layout.addWidget(motor_setting_frame)

        # 参数设置
        params_frame = QFrame()
        params_frame.setFrameShape(QFrame.Shape.StyledPanel)
        params_frame.setFrameShadow(QFrame.Shadow.Raised)
        params_layout = QGridLayout()

        params_label = QLabel("<h3>参数设置</h3>")
        params_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        params_layout.addWidget(params_label, 0, 0, 1, 2)

        set_waveform_label = QLabel("插值方法：")
        set_waveform_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        params_layout.addWidget(set_waveform_label, 1, 0)

        self.select_method = QComboBox()
        self.select_method.addItems(["Lagrange", "Cubic Spline"])
        self.select_method.currentTextChanged.connect(lambda: (
            self.config.__setitem__("插值方法", self.select_method.currentText()),
            self.waveform_area.update(),
            self.waveform_area.points_changed.emit(),  # 发射信号触发插值函数重计算
        ))
        params_layout.addWidget(self.select_method, 1, 1)

        self.set_offset = QDoubleSpinBox()
        self.set_offset.setRange(0, self.motor_pool.get(self.motor_selection.currentText()).get("导轨长度"))
        self.set_offset.setDecimals(1)
        self.set_offset.setSingleStep(0.1)
        self.set_offset.setValue(self.config.get("偏移量"))
        self.set_offset.setSuffix(" mm")
        self.set_offset.valueChanged.connect(lambda: (
            self.config.__setitem__("偏移量", self.set_offset.value()),
            self.update_mock_waveform(),
        ))
        params_layout.addWidget(QLabel("偏移量："), 2, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        params_layout.addWidget(self.set_offset, 2, 1)

        self.set_frequency = QDoubleSpinBox()
        self.set_frequency.setSingleStep(0.01)
        self.set_frequency.setValue(self.config.get("频率"))
        self.set_frequency.setSuffix(" Hz")
        self.set_frequency.valueChanged.connect(lambda: (
            self.config.__setitem__("频率", self.set_frequency.value()),
            self.update_mock_waveform(),
        ))
        params_layout.addWidget(QLabel("频率："), 3, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        params_layout.addWidget(self.set_frequency, 3, 1)

        self.set_amplitude = QSpinBox()
        self.set_amplitude.setRange(0, 1000)
        self.set_amplitude.setSingleStep(1)
        self.set_amplitude.setValue(self.config.get("幅值比例"))
        self.set_amplitude.setSuffix(" %")
        self.set_amplitude.valueChanged.connect(lambda: (
            self.config.__setitem__("幅值比例", self.set_amplitude.value()),
            self.update_mock_waveform(),
        ))
        params_layout.addWidget(QLabel("幅值比例："), 4, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        params_layout.addWidget(self.set_amplitude, 4, 1)

        params_frame.setLayout(params_layout)
        middle_layout.addWidget(params_frame)

        """
        上区域 - 右布局
        """
        right_layout = QVBoxLayout()

        # 电机初始化
        motor_init_frame = QFrame()
        motor_init_frame.setFrameShape(QFrame.Shape.StyledPanel)
        motor_init_frame.setFrameShadow(QFrame.Shadow.Raised)
        motor_init_layout = QGridLayout()

        motor_init_label = QLabel("<h3>电机初始化</h3>")
        motor_init_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_init_layout.addWidget(motor_init_label, 0, 0, 1, 2)

        self.status_light = QLabel()
        self.status_light.setFixedSize(20, 20)
        self.status_light.setStyleSheet("background-color: red; border-radius: 10px;")
        motor_init_layout.addWidget(self.status_light, 1, 0, 2, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        self.activate_button = QPushButton()
        self.activate_button.setText("启动")
        self.activate_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前未连接电机！"))
        motor_init_layout.addWidget(self.activate_button, 1, 1)

        self.localization_button = QPushButton()
        self.localization_button.setText("复位")
        self.localization_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前选中电机未启动！"))
        motor_init_layout.addWidget(self.localization_button, 2, 1)

        self.move_to_button = QPushButton()
        self.move_to_button.setText("移动至")
        self.move_to_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前选中电机未启动！"))
        motor_init_layout.addWidget(self.move_to_button, 3, 0)

        self.set_movement_distance = QDoubleSpinBox()
        self.set_movement_distance.setDecimals(1)
        self.set_movement_distance.setSingleStep(0.1)
        self.set_movement_distance.setValue(0)
        self.set_movement_distance.setSuffix(" mm")
        motor_init_layout.addWidget(self.set_movement_distance, 3, 1)

        motor_init_frame.setLayout(motor_init_layout)
        right_layout.addWidget(motor_init_frame)

        # 电机运行
        motor_running_frame = QFrame()
        motor_running_frame.setFrameShape(QFrame.Shape.StyledPanel)
        motor_running_frame.setFrameShadow(QFrame.Shadow.Raised)
        motor_running_layout = QGridLayout()

        motor_running_label = QLabel("<h3>电机运行</h3>")
        motor_running_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_running_layout.addWidget(motor_running_label, 0, 0, 1, 2)

        self.start_button = QPushButton()
        self.start_button.setText("开始")
        self.start_button.setStyleSheet("QPushButton { height: 2.5em; } ")
        self.start_button.clicked.connect(self.send_data)
        motor_running_layout.addWidget(self.start_button, 1, 0, 2, 2)

        self.stop_button = QPushButton()
        self.stop_button.setText("停止")
        self.stop_button.setStyleSheet("QPushButton { height: 2.5em; } ")
        self.stop_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前选中电机未启动！"))
        motor_running_layout.addWidget(self.stop_button, 3, 0, 2, 2)

        motor_running_frame.setLayout(motor_running_layout)
        right_layout.addWidget(motor_running_frame)

        """
        上区域 - 缩放因子
        """
        upper_layout.addLayout(left_layout)
        upper_layout.addLayout(middle_layout)
        upper_layout.addLayout(right_layout)
        upper_layout.setStretch(0, 4)
        upper_layout.setStretch(1, 1)
        upper_layout.setStretch(2, 1)
        main_layout.addLayout(upper_layout)

        """
        下区域
        """
        # 多页面区域
        multi_widget_area = QTabWidget()

        # 反馈波形页
        feedback_area = QWidget()
        feedback_layout = QVBoxLayout(feedback_area)

        record_layout = QHBoxLayout()
        record_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        record_status = QLabel()
        record_status.setFixedSize(20, 20)
        record_status.setStyleSheet("background-color: red; border-radius: 10px;")
        record_layout.addWidget(record_status)

        record_button = QPushButton("开始录制")
        record_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前未连接电机！"))
        record_layout.addWidget(record_button)

        feedback_layout.addLayout(record_layout)

        feedback_chart = QChart()
        feedback_chart_view = QChartView(feedback_chart)
        feedback_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        feedback_chart.legend().hide()
        feedback_layout.addWidget(feedback_chart_view)

        series = QLineSeries()  # 测试波形
        for i in range(100):
            x = i
            y = 50 * (1 + 0.5 * math.sin(x * 0.1))
            series.append(QPointF(x, y))
        feedback_chart.addSeries(series)
        feedback_chart.createDefaultAxes()

        multi_widget_area.addTab(feedback_area, "反馈波形")

        # 模拟波形页
        self.mock_chart = QChart()
        mock_chart_view = QChartView(self.mock_chart)
        mock_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.mock_chart.legend().hide()
        multi_widget_area.addTab(mock_chart_view, "模拟波形")

        # 虚拟波形的坐标轴
        self.mock_axis_x = QValueAxis()
        self.mock_axis_y = QValueAxis()
        self.mock_axis_x.setRange(0, 1)  # X轴范围
        self.mock_axis_y.setRange(0,
                                  self.motor_pool.get(self.motor_selection.currentText()).get("导轨长度"))  # Y轴范围
        self.mock_axis_x.setTickCount(24)  # X轴刻度线数量
        self.mock_axis_y.setTickCount(9)  # Y轴刻度线数量
        self.mock_chart.addAxis(self.mock_axis_x, Qt.AlignmentFlag.AlignBottom)
        self.mock_chart.addAxis(self.mock_axis_y, Qt.AlignmentFlag.AlignLeft)

        # 多项式页
        self.formulas_area = FormulasDisplay(self.config)
        self.formulas_area.status_message.connect(self.update_status)
        multi_widget_area.addTab(self.formulas_area, "多项式")

        lower_layout.addWidget(multi_widget_area)
        main_layout.addLayout(lower_layout)

        """
        主布局 - 缩放因子
        """
        main_layout.setStretch(0, 1)
        main_layout.setStretch(1, 1)

    def update_status(self, text: str):
        """
        更新状态栏信息
        :param text: 显示的文本
        """
        current_time = datetime.now().strftime("%H:%M:%S")
        self.status_bar.showMessage(f"{current_time}: {text}", 0)

    @Slot()
    def send_data(self):
        """
        波形数据发送功能实现
        """
        if not self.config.get("有效性检查结果"):
            QMessageBox.warning(self, "警告", "波形异常，无法设置参数，请检查！")
            return

        QMessageBox.warning(self, "警告", "当前选中电机未启动！")
        # self.update_status("电机运行参数设置成功！")

    @Slot()
    def update_validity_display(self, result: bool):
        """
        更新有效性检查结果功能实现
        :param result: 有效性检查结果
        """
        if result:
            self.validity_display_area.setText("波形正常，可以执行！")
            self.validity_display_area.setStyleSheet(
                '''
                background-color: green;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding-top: 5px;
                padding-bottom: 5px;
                '''
            )
        else:
            self.validity_display_area.setText("波形异常，无法执行！")
            self.validity_display_area.setStyleSheet(
                '''
                background-color: red;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding-top: 5px;
                padding-bottom: 5px;
                '''
            )

    @Slot()
    def read_waveform(self):
        """
        从文件中读取波形数据功能实现
        """
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        fileName, _ = QFileDialog.getOpenFileName(self, "读取波形", "", "DAT Files (*.dat);;All Files (*)",
                                                  options=options)
        if fileName:
            try:
                with open(fileName, "rb") as file:
                    self.config.update(pickle.load(file))
                    self.select_method.setCurrentText(self.config["插值方法"])
                    self.set_offset.setValue(self.config["偏移量"])
                    self.set_frequency.setValue(self.config["频率"])
                    self.set_amplitude.setValue(self.config["幅值"])
                    self.waveform_area.update()
                    self.waveform_area.points_changed.emit()  # 发射信号触发公式绘制
                self.update_status(f"成功从 {fileName} 读取波形数据！")
            except Exception as e:
                QMessageBox.warning(self, "警告", f"读取波形数据出错: {e}")

    @Slot()
    def save_waveform(self):
        """
        保存波形数据到文件功能实现
        """
        options = QFileDialog.Options()
        fileName, _ = QFileDialog.getSaveFileName(self, "保存波形", "", "DAT Files (*.dat);;All Files (*)",
                                                  options=options)
        if fileName:
            try:
                with open(fileName, "wb") as file:
                    pickle.dump(self.config, file)
                self.update_status(f"保存波形数据到 {fileName} ！")
            except Exception as e:
                QMessageBox.warning(self, "警告", f"保存波形数据时出错: {e}")

    @Slot()
    def open_dialog(self):
        """
        打开设置窗口功能实现
        """
        dialog = SettingDialog(self.client)
        dialog.status_message.connect(self.update_status)
        dialog.exec()

    @Slot()
    def update_mock_waveform(self):
        """
        更新虚拟波形功能实现
        """
        self.mock_chart.removeAllSeries()
        series = QLineSeries()
        period = int(self.mock_axis_x.max() * self.config.get("频率") + 1)
        for i in range(period):
            for x, y in self.waveform_area.interpolated_points:
                # X坐标变换
                processed_x = (x + i) / self.config.get("频率")

                # Y坐标变换
                absolute_y = y * self.motor_pool.get(self.motor_selection.currentText()).get("导轨长度")  # 换算绝对坐标
                processed_y = (absolute_y * self.config.get("幅值比例") / 100.0) + self.config.get("偏移量")  # 偏移和增幅
                if (self.mock_axis_x.min() <= processed_x <= self.mock_axis_x.max()
                        and self.mock_axis_y.min() <= processed_y <= self.mock_axis_y.max()):
                    series.append(processed_x, processed_y)
        self.mock_chart.addSeries(series)
        series.attachAxis(self.mock_axis_x)
        series.attachAxis(self.mock_axis_y)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
