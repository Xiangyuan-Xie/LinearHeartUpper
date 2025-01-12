import math
import sys
from datetime import datetime
from threading import Thread

import numpy as np
from PySide6.QtCharts import QChart, QChartView, QLineSeries
from PySide6.QtCore import Qt, QThreadPool, Slot, QPointF
from PySide6.QtGui import QPainter, QPen, QMouseEvent, QColor, QFont, QPainterPath, QPixmap, QBrush
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QScrollArea, QMainWindow, QHBoxLayout, QComboBox, \
    QLabel, QFrame, QGridLayout, QDoubleSpinBox, QPushButton, QTabWidget, QMessageBox
from flask import Flask
from flask_cors import CORS
from matplotlib import rcParams
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from multi_thread import *


class WaveformArea(QWidget):
    points_changed = Signal(list)

    def __init__(self, config):
        super().__init__()
        self.points = [(0.0, 0.0), (1.0, 0.0)]  # 插值点坐标
        self.interpolated_points = []  # 插值曲线点坐标
        self.x_range = 1  # X轴范围
        self.y_range = 1  # Y轴范围
        self.static_pixmap = None  # 缓存静态内容
        self.dragging_point = None  # 当前拖动点的索引
        self.config = config  # 用户配置
        self.setMouseTracking(True)  # 启用鼠标跟踪，捕捉鼠标移动事件

    def add_point(self, x, y):
        """
        用户添加插值点功能实现
        :param x: 插值点X坐标
        :param y: 插值点Y坐标
        """
        self.points.append((x, y))

    def remove_point(self):
        """
        用户移除插值点功能实现
        """
        if len(self.points) > 2:
            self.points.pop()

    def interpolate(self, num_points=100):
        """
        插值计算功能实现
        :param num_points: 绘制插值曲线点的数量，默认为100
        :return: list(zip(x_new, y_new))，每个元素代表一个插值点
        """
        if len(self.points) < 2:
            return []

        method = self.config.get("插值方法", 'Lagrange')

        # 拉格朗日插值
        if method == "Lagrange":
            x_vals, y_vals = zip(*self.points)
            poly = lagrange(x_vals, y_vals)
            x_new = np.linspace(min(x_vals), max(x_vals), num_points)
            y_new = poly(x_new)

        # 三次样条插值
        elif method == "Cubic Spline":
            sorted_points = sorted(self.points, key=lambda p: p[0])
            x_vals, y_vals = zip(*sorted_points)
            poly = CubicSpline(x_vals, y_vals)
            x_new = np.linspace(min(x_vals), max(x_vals), num_points)
            y_new = poly(x_new)

        # 未知插值方法
        else:
            return []

        return list(zip(x_new, y_new))

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
        for index, point in enumerate(self.points):
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
        if len(self.points) > 1:
            # 计算插值曲线点集
            self.interpolated_points = self.interpolate()

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
        tick_interval = 30  # 刻度间隔
        for x in range(50 + tick_interval, self.width() - 50, tick_interval):  # 垂直网格线
            static_painter.drawLine(x, 50, x, self.height() - 50)
        for y in range(50 + tick_interval, self.height() - 50, tick_interval):  # 水平网格线
            static_painter.drawLine(50, y, self.width() - 50, y)

        # 设置坐标轴标题的字体和颜色
        title_font = QFont('Times New Roman', 12, QFont.Weight.Bold)  # 加粗
        static_painter.setFont(title_font)
        title_color = QColor(0, 0, 0)  # 黑色
        static_painter.setPen(QPen(title_color))

        # 绘制坐标轴标题
        static_painter.drawText(30, self.height() - 30, 'O')  # 原点
        static_painter.drawText(self.width() - 53, self.height() - 30, "1")  # 周期最大值
        static_painter.drawText(30, 55, "1")  # 幅值最大值
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
                    self.points_changed.emit(self.points)

                # 不存在正在拖动的点
                else:
                    tolerance = 8  # 容忍范围内视为可拖动，单位为像素
                    for i, (px, py) in enumerate(self.points):
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
                        self.points_changed.emit(self.points)

                # 更新控件显示
                self.update()

        # 右键
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self.points) > 2:
                self.remove_point()
                self.update()
                self.points_changed.emit(self.points)

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
                self.points[self.dragging_point] = (scaled_x, scaled_y)
                self.update()


class FormulasDisplay(QWidget):
    status_message = Signal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.thread_pool = QThreadPool.globalInstance()
        self.html_content_forward = r'''
            <!DOCTYPE html>
            <html lang="en">
                <head>
                    <script id="MathJax-script" async src="http://localhost:5000/MathJax/es5/tex-mml-chtml.js"></script>
                    <title></title>
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

        # 滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        # 公式控件
        # self.figure = Figure()
        # self.canvas = FigureCanvas(self.figure)
        # self.scroll_area.setWidget(self.canvas)
        # layout.addWidget(self.scroll_area)

        # 浏览器
        self.webview = QWebEngineView()
        self.webview.setHtml(self.html_content_forward + self.html_content_backward)
        layout.addWidget(self.webview)

        self.setLayout(layout)

    @Slot(list)
    def update_polynomial(self, points):
        worker = ExpressionWorker()
        worker.result_ready.connect(self.on_result_ready)
        task = ExpressionTask(points, self.config.get("插值方法", 'Lagrange'), worker)
        self.thread_pool.start(task)

    @Slot(tuple)
    def on_result_ready(self, result):
        if result is None:
            self.status_message.emit("插值计算失败：使用了无效的插值方法！")
            return

        html_context = self.html_content_forward + result[1] + self.html_content_backward
        self.webview.setHtml(html_context)

        # # 绘制公式
        # self.figure.clear()
        # ax = self.figure.add_subplot(111)
        # ax.axis('off')
        # text_obj = ax.text(0.5, 0.5, f"${result[1]}$", fontsize=16, ha='center', va='center')
        #
        # # 获取公式的边界框
        # bbox = text_obj.get_window_extent().transformed(self.figure.dpi_scale_trans.inverted())
        # formula_width = bbox.width * self.figure.dpi
        #
        # # 获取当前滚动区域的宽度
        # scroll_area_width = self.scroll_area.width()
        #
        # # 检查公式的宽度是否超出 canvas 宽度
        # if formula_width > scroll_area_width:
        #     # 动态调整 FigureCanvas 的宽度
        #     self.canvas.setFixedWidth(int(formula_width))
        #
        #     # 计算滚动条的新位置，设定为公式的中间
        #     scroll_position = (formula_width - scroll_area_width) / 2
        #
        #     # 将滚动条移动到中间
        #     self.scroll_area.horizontalScrollBar().setValue(int(scroll_position))
        #
        # self.canvas.draw()
        self.status_message.emit(f"{result[0]}插值方法计算完成！")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = {
            "插值方法": "Lagrange",
            "偏移量": 0.00,
            "频率": 1.00,
            "幅值": 1.00,
        }

        # 设置窗口标题
        self.setWindowTitle("直线电机心脏驱动系统")
        self.setGeometry(100, 100, 1200, 675)

        # 布局
        main_layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 状态栏
        self.status_bar = self.statusBar()

        '''
        左区域
        '''
        # 波形图区域
        self.waveform_area = WaveformArea(self.config)
        self.waveform_area.setMinimumHeight(400)
        self.waveform_area.points_changed.connect(lambda points: (
            self.formulas_area.update_polynomial(points),
            self.update_status(f"正在使用{self.config.get('插值方法', '未知方法')}进行计算！") if len(points) > 2 else self.update_status(f"当前点的数量不足，无法计算！")
        ))
        left_layout.addWidget(self.waveform_area)

        # 多控件区域
        multi_widget_area = QTabWidget()

        # 反馈波形页
        chart = QChart()
        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        multi_widget_area.addTab(chart_view, "反馈波形")

        # 测试波形
        series = QLineSeries()
        series.setName("测试虚拟波形")
        for i in range(100):
            x = i
            y = 50 * (1 + 0.5 * math.sin(x * 0.1))
            series.append(QPointF(x, y))
        chart.addSeries(series)
        chart.createDefaultAxes()

        # 多项式页
        self.formulas_area = FormulasDisplay(self.config)
        self.formulas_area.status_message.connect(self.update_status)
        rcParams['mathtext.fontset'] = 'stix'  # 使用STIX字体集
        rcParams['mathtext.rm'] = 'serif'  # 设置正常文本为serif字体
        rcParams['mathtext.it'] = 'serif'  # 设置斜体字体
        rcParams['mathtext.bf'] = 'serif'  # 设置粗体字体
        multi_widget_area.addTab(self.formulas_area, "多项式")

        left_layout.addWidget(multi_widget_area)

        '''
        右区域
        '''
        # 电机选择
        motor_frame = QFrame()
        motor_frame.setFrameShape(QFrame.Shape.StyledPanel)
        motor_frame.setFrameShadow(QFrame.Shadow.Raised)
        motor_layout = QVBoxLayout()  # 使用垂直布局

        select_motor_label = QLabel("选择电机")
        select_motor_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        select_motor = QComboBox()
        motors = ["所有电机", "1号电机"]
        select_motor.addItems(motors)

        motor_layout.addWidget(select_motor_label)
        motor_layout.addWidget(select_motor)
        motor_frame.setLayout(motor_layout)
        right_layout.addWidget(motor_frame)

        # 插值方法
        method_frame = QFrame()
        method_frame.setFrameShape(QFrame.Shape.StyledPanel)
        method_frame.setFrameShadow(QFrame.Shadow.Raised)
        method_layout = QGridLayout()

        set_waveform_label = QLabel("设置插值方法")
        set_waveform_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        method_layout.addWidget(set_waveform_label, 0, 0, 1, 2)

        self.select_method = QComboBox()
        self.select_method.addItems(["Lagrange", "Cubic Spline"])
        self.select_method.currentIndexChanged.connect(self.update_method)
        method_layout.addWidget(self.select_method, 2, 0, 1, 2)

        method_frame.setLayout(method_layout)
        right_layout.addWidget(method_frame)

        # 周期运行参数
        params_frame = QFrame()
        params_frame.setFrameShape(QFrame.Shape.StyledPanel)
        params_frame.setFrameShadow(QFrame.Shadow.Raised)
        params_layout = QGridLayout()

        set_params_label = QLabel("设置周期运行参数")
        set_params_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        params_layout.addWidget(set_params_label, 0, 0, 1, 2)

        self.set_offset = QDoubleSpinBox()
        self.set_offset.setSingleStep(0.01)
        self.set_offset.setValue(self.config.get("偏移量", 0.00))
        self.set_offset.valueChanged.connect(lambda: self.config.__setitem__("偏移量", self.set_offset.value()))
        params_layout.addWidget(self.set_offset, 1, 0)
        params_layout.addWidget(QLabel("偏移量(mm)"), 1, 1)

        self.set_frequency = QDoubleSpinBox()
        self.set_frequency.setSingleStep(0.01)
        self.set_frequency.setValue(self.config.get("频率", 1.00))
        self.set_frequency.valueChanged.connect(lambda: self.config.__setitem__("频率", self.set_frequency.value()))
        params_layout.addWidget(self.set_frequency, 2, 0)
        params_layout.addWidget(QLabel("频率(Hz)"), 2, 1)

        self.set_amplitude = QDoubleSpinBox()
        self.set_amplitude.setSingleStep(0.01)
        self.set_amplitude.setValue(self.config.get("幅值", 1.00))
        self.set_amplitude.valueChanged.connect(lambda: self.config.__setitem__("幅值", self.set_amplitude.value()))
        params_layout.addWidget(self.set_amplitude, 3, 0)
        params_layout.addWidget(QLabel("幅值(mm)"), 3, 1)

        params_frame.setLayout(params_layout)
        right_layout.addWidget(params_frame)

        # 电机初始化
        motor_init_frame = QFrame()
        motor_init_frame.setFrameShape(QFrame.Shape.StyledPanel)
        motor_init_frame.setFrameShadow(QFrame.Shadow.Raised)
        motor_init_layout = QGridLayout()

        motor_init_label = QLabel("电机初始化")
        motor_init_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_init_layout.addWidget(motor_init_label, 0, 0, 1, 2)

        self.status_light = QLabel()
        self.status_light.setFixedSize(20, 20)
        self.status_light.setStyleSheet("background-color: red; border-radius: 10px;")
        motor_init_layout.addWidget(self.status_light, 1, 0, alignment=Qt.AlignmentFlag.AlignCenter)

        self.activate_button = QPushButton()
        self.activate_button.setText("启动")
        self.activate_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前未连接电机！"))
        motor_init_layout.addWidget(self.activate_button, 1, 1)

        self.localization_button = QPushButton()
        self.localization_button.setText("定位")
        self.localization_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前选中电机未启动！"))
        motor_init_layout.addWidget(self.localization_button, 2, 0, 1 ,2)

        self.move_to_button = QPushButton()
        self.move_to_button.setText("移动至")
        self.move_to_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前选中电机未启动！"))
        motor_init_layout.addWidget(self.move_to_button, 3, 0, 1, 2)

        self.set_movement_distance = QDoubleSpinBox()
        self.set_movement_distance.setSingleStep(0.01)
        self.set_movement_distance.setValue(0)
        motor_init_layout.addWidget(self.set_movement_distance, 4, 0)
        motor_init_layout.addWidget(QLabel("位置(mm)"), 4, 1)

        motor_init_frame.setLayout(motor_init_layout)
        right_layout.addWidget(motor_init_frame)

        # 电机运行
        motor_running_frame = QFrame()
        motor_running_frame.setFrameShape(QFrame.Shape.StyledPanel)
        motor_running_frame.setFrameShadow(QFrame.Shadow.Raised)
        motor_running_layout = QGridLayout()

        motor_running_label = QLabel("电机运行")
        motor_running_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_running_layout.addWidget(motor_running_label, 0, 0, 1, 2)

        self.start_button = QPushButton()
        self.start_button.setText("开始")
        self.start_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前选中电机未启动！"))
        motor_running_layout.addWidget(self.start_button, 1, 0, 1, 2)

        self.stop_to_button = QPushButton()
        self.stop_to_button.setText("停止至")
        self.stop_to_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前选中电机未启动！"))
        motor_running_layout.addWidget(self.stop_to_button, 2, 0, 1, 2)

        self.set_stop_distance = QDoubleSpinBox()
        self.set_stop_distance.setSingleStep(0.01)
        self.set_stop_distance.setValue(0)
        motor_running_layout.addWidget(self.set_stop_distance, 3, 0)
        motor_running_layout.addWidget(QLabel("位置(mm)"), 3, 1)

        self.stop_button = QPushButton()
        self.stop_button.setText("停止")
        self.stop_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前选中电机未启动！"))
        motor_running_layout.addWidget(self.stop_button, 4, 0, 1, 2)

        self.set_params_button = QPushButton()
        self.set_params_button.setText("设置参数")
        self.set_params_button.clicked.connect(self.send_data)
        motor_running_layout.addWidget(self.set_params_button, 5, 0, 1, 2)

        motor_running_frame.setLayout(motor_running_layout)
        right_layout.addWidget(motor_running_frame)

        # 布局
        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)
        central_widget.setLayout(main_layout)

    def update_status(self, text):
        """
        更新状态栏信息
        :param text: 显示的文本
        """
        current_time = datetime.now().strftime("%H:%M:%S")
        self.status_bar.showMessage(f"{current_time}: {text}", 0)

    @Slot()
    def update_method(self):
        """
        插值方法修改后重插值功能实现
        """
        self.config["插值方法"] = self.select_method.currentText()
        self.waveform_area.update()
        self.waveform_area.points_changed.emit(self.waveform_area.points)  # 发射信号触发新方法重绘

    @Slot()
    def send_data(self):
        for _, py in self.waveform_area.interpolated_points:
            if py > 1 or py < 0:
                QMessageBox.warning(self, "警告", "波形超出有效范围，无法设置参数，请检查！")
                return

        QMessageBox.warning(self, "警告", "当前选中电机未启动！")
        # self.update_status("电机运行参数设置成功！")


if __name__ == "__main__":
    # MathJax服务器
    server = Flask(__name__, static_folder="./MathJax")
    CORS(server)  # 允许跨域请求
    mathjax_thread = Thread(target=lambda: server.run(host='0.0.0.0', port=5000, threaded=True))
    mathjax_thread.daemon = True
    mathjax_thread.start()

    # UI界面
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
