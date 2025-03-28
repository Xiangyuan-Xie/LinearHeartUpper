import math
import pickle
import sys
from datetime import datetime
from threading import Thread
from typing import Optional

import numpy as np
import pandas as pd
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt, QPointF, QThreadPool, Slot, QDir
from PySide6.QtGui import QAction, QPainter
from PySide6.QtWidgets import (QApplication, QMainWindow, QHBoxLayout, QComboBox, QFrame, QDoubleSpinBox,
                               QTabWidget, QMenuBar, QMenu, QFileDialog, QSpinBox, QVBoxLayout, QWidget, QLabel,
                               QGridLayout, QPushButton, QMessageBox)
from flask import Flask
from flask_cors import CORS
from pymodbus.client import ModbusTcpClient

from communication import interval_encode, SplineCoefficientCompressor
from widget import WaveformArea, FormulasDisplay, ConnectDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = {
            "插值方法": "Lagrange",
            "插值点集": [(0.0, 0.0), (1.0, 0.0)],
            "偏移量": 0.0,
            "频率": 1.0,
            "幅值比例": 100,
            "规则检查结果": True,
        }
        self.motor_pool = {
            "1号电机": {
                "导轨长度": 100.0,
            }
        }
        self.client: Optional[ModbusTcpClient] = None
        self.thread_pool = QThreadPool.globalInstance()
        self.compressor = SplineCoefficientCompressor()

        # MathJax服务器
        server = Flask(__name__, static_folder="./MathJax")
        CORS(server)  # 允许跨域请求
        mathjax_thread = Thread(target=lambda: server.run(host='0.0.0.0', port=5000, threaded=True))
        mathjax_thread.daemon = True
        mathjax_thread.start()

        # 设置窗口标题
        self.setWindowTitle("直线电机心脏驱动系统PC端")
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

        read_waveform_action = QAction("读取波形文件", self)
        read_waveform_action.triggered.connect(self._read_waveform_file)
        file_menu.addAction(read_waveform_action)

        save_waveform_action = QAction("保存波形文件", self)
        save_waveform_action.triggered.connect(self._save_waveform_file)
        file_menu.addAction(save_waveform_action)

        # 连接
        connect_action = QAction("连接", self)
        connect_action.triggered.connect(self._open_dialog)
        menu_bar.addAction(connect_action)

        # 导出
        export_menu = QMenu("导出", self)
        menu_bar.addMenu(export_menu)

        export_mock_waveform_action = QAction("导出虚拟波形", self)
        export_mock_waveform_action.triggered.connect(self.export_mock_waveform)
        export_menu.addAction(export_mock_waveform_action)

        """
        上区域 - 左布局
        """
        left_layout = QVBoxLayout()

        # 波形图区域
        self.waveform_area = WaveformArea(self.config)
        self.waveform_area.points_changed.connect(lambda: (
            self.formulas_area.create_polynomial_task(self.config["插值点集"]),
            self.update_status(f"正在使用{self.config.get('插值方法')}进行计算！"),
        ))
        self.waveform_area.rule_check_result.connect(lambda result: (
            self.config.__setitem__("规则检查结果", result),
            self._update_rule_check_result_display(result),
            self._update_mock_waveform_display(),
        ))
        left_layout.addWidget(self.waveform_area)

        # 有效性检测区域
        self.validity_display_area = QLabel()
        self.validity_display_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_rule_check_result_display(self.config.get("规则检查结果"))
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

        preview_duration_label = QLabel("预览时长：")
        preview_duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_setting_layout.addWidget(preview_duration_label, 3, 0, alignment=Qt.AlignmentFlag.AlignCenter)

        self.preview_duration = QDoubleSpinBox()
        self.preview_duration.setRange(0, 100)
        self.preview_duration.setDecimals(1)
        self.preview_duration.setSingleStep(0.1)
        self.preview_duration.setValue(1.0)
        self.preview_duration.setSuffix(" s")
        self.preview_duration.valueChanged.connect(lambda: (
            self.mock_axis_x.setRange(0, self.preview_duration.value()),
            self._update_mock_waveform_display(),
        ))
        motor_setting_layout.addWidget(self.preview_duration, 3, 1)

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
            self._update_mock_waveform_display(),
        ))
        params_layout.addWidget(QLabel("偏移量："), 2, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        params_layout.addWidget(self.set_offset, 2, 1)

        self.set_frequency = QDoubleSpinBox()
        self.set_frequency.setSingleStep(0.01)
        self.set_frequency.setValue(self.config.get("频率"))
        self.set_frequency.setSuffix(" Hz")
        self.set_frequency.valueChanged.connect(lambda: (
            self.config.__setitem__("频率", self.set_frequency.value()),
            self._update_mock_waveform_display(),
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
            self._update_mock_waveform_display(),
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
        # self.stop_button.clicked.connect(lambda: QMessageBox.warning(self, "警告", "当前选中电机未启动！"))
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
        # if not self.config.get("规则检查结果"):
        #     QMessageBox.warning(self, "警告", "波形异常，无法设置参数，请检查！")
        #     return
        #
        # QMessageBox.warning(self, "警告", "当前选中电机未启动！")
        # self.update_status("电机运行参数设置成功！")
        # if self.client is not None and self.client.is_socket_open():
        #     self.client.write_registers(0, [1, 2, 3, 4, 5], slave=1)
        # else:
        #     QMessageBox.warning(self, "警告", "当前选中电机未启动！")
        polynomial_object = self.formulas_area.polynomial_object
        if polynomial_object[0] == "Lagrange":
            packet = []
        elif polynomial_object[0] == "Cubic Spline":
            encoded_interval_matrix = interval_encode(polynomial_object[1].x[:-1], polynomial_object[1].x[1:])
            encoded_coefficient_matrix = self.compressor.compress(polynomial_object[1].c.T)
            packet = np.concatenate(np.column_stack([encoded_interval_matrix, encoded_coefficient_matrix]))
        else:
            raise ValueError("试图使用未定义的插值类型！")

        print(packet)

        self.client.write_registers(0, packet, slave=1)


    @Slot()
    def _update_rule_check_result_display(self, result: bool):
        """
        更新规则检查结果功能实现
        :param result: 规则检查结果
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
    def _read_waveform_file(self):
        """
        从文件中读取波形数据功能实现
        """
        dialog = QFileDialog(parent=self, acceptMode=QFileDialog.AcceptMode.AcceptOpen, defaultSuffix="dat",
                             options=QFileDialog.Option.DontUseNativeDialog | QFileDialog.Option.ReadOnly)
        dialog.setWindowTitle("读取波形")
        dialog.setNameFilter("DAT Files (*.dat);;All Files (*)")

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                file_path = selected_files[0]

                normalized_path = QDir.toNativeSeparators(file_path)  # 路径标准化处理（跨平台兼容）

                try:
                    with open(normalized_path, "rb") as file:
                        self.config.update(pickle.load(file))
                        self.select_method.setCurrentText(self.config["插值方法"])
                        self.set_offset.setValue(self.config["偏移量"])
                        self.set_frequency.setValue(self.config["频率"])
                        self.set_amplitude.setValue(self.config["幅值比例"])
                        self.waveform_area.update()
                        self.waveform_area.points_changed.emit()  # 发射信号触发公式绘制
                    self.update_status(f"成功从 {normalized_path} 读取波形数据！")
                except Exception as e:
                    QMessageBox.critical(self, "警告", f"读取波形数据出错: {e}")


    @Slot()
    def _save_waveform_file(self):
        """
        保存波形数据到文件功能实现
        """
        dialog = QFileDialog(parent=self, acceptMode=QFileDialog.AcceptMode.AcceptSave, defaultSuffix="dat",
                             options=QFileDialog.Option.DontUseNativeDialog | QFileDialog.Option.ReadOnly)
        dialog.setWindowTitle("保存波形")
        dialog.setNameFilter("DAT Files (*.dat);;All Files (*)")

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                file_path = selected_files[0]

                normalized_path = QDir.toNativeSeparators(file_path)  # 路径标准化处理（跨平台兼容）

                try:
                    with open(normalized_path, "wb") as f:
                        pickle.dump(self.config, f)
                    self.update_status(f"保存波形数据到 {normalized_path} ！")
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"保存波形数据时出错: {e}")


    @Slot()
    def _open_dialog(self):
        """
        打开设置窗口功能实现
        """
        dialog = ConnectDialog()
        dialog.status_message.connect(self.update_status)
        dialog.connection_info.connect(self._create_client)
        dialog.exec()

    @Slot()
    def _update_mock_waveform_display(self):
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

    @Slot()
    def export_mock_waveform(self):
        """
        导出虚拟波形
        """
        dialog = QFileDialog(parent=self, acceptMode=QFileDialog.AcceptMode.AcceptSave, defaultSuffix="csv",
                             options=QFileDialog.Option.DontUseNativeDialog | QFileDialog.Option.ReadOnly)
        dialog.setWindowTitle("导出虚拟波形")
        dialog.setNameFilter("CSV Files (*.csv);;All Files (*)")

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                file_path = selected_files[0]

                normalized_path = QDir.toNativeSeparators(file_path)  # 路径标准化处理（跨平台兼容）

                try:
                    result = []
                    for x, y in self.waveform_area.interpolated_points:
                        # X坐标变换
                        processed_x = x / self.config.get("频率")

                        # Y坐标变换
                        absolute_y = y * self.motor_pool.get(self.motor_selection.currentText()).get("导轨长度")  # 换算绝对坐标
                        processed_y = (absolute_y * self.config.get("幅值比例") / 100.0) + self.config.get("偏移量")  # 偏移和增幅

                        result.append(
                            (processed_x, max(self.mock_axis_y.min(), min(processed_y, self.mock_axis_y.max()))))

                    df = pd.DataFrame(result, columns=['x', 'y'])
                    df.astype({'x': 'float32', 'y': 'float32'}).to_csv(
                        normalized_path,
                        index=False,
                        float_format='%.4f'  # 统一小数位数
                    )
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"导出虚拟波形时出错: {e}！")

    @Slot(str, int)
    def _create_client(self, host: str, port: int):
        """
        新建ModbusTcpClient功能实现
        :param host: PLC的连接IP地址
        :param port: PLC的连接端口
        """
        self.client = ModbusTcpClient(host=host, port=port)
        if self.client.connect() and self.client.is_socket_open():
            self.update_status("PLC连接成功！")
        else:
            self.update_status("PLC连接失败！")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
