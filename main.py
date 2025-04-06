import pickle
import sys
from datetime import datetime
from multiprocessing import Process
from threading import Thread, Event
from typing import Optional

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QThreadPool, Slot, QDir
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QMainWindow, QHBoxLayout, QComboBox, QFrame, QDoubleSpinBox,
                               QTabWidget, QMenuBar, QMenu, QFileDialog, QSpinBox, QVBoxLayout, QWidget, QLabel,
                               QGridLayout, QPushButton, QMessageBox, QSlider)
from pymodbus.client import ModbusTcpClient

from common import (Interpolation, InterpolationManager, RegisterAddress, MotorPowerStatus, MotorOperationStatus,
                    ConnectionStatus)
from communication import float_to_fixed, split_array, process_response, fixed_to_float, check_client_status
from mathjax_server import run_server
from task import ConnectionTask, TaskRunner
from widget.chart import FeedbackWaveformChart, MockWaveformChart
from widget.connection_dialog import ConnectionDialog
from widget.latex_board import LatexBoard
from widget.status_light import StatusLight
from widget.status_manager import ConnectionStatusManager, RecordStatusManager
from widget.waveform_modulator import WaveformModulator, WaveformStatus


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = {
            "插值方法": Interpolation.Akima,
            "插值点集": [(0.0, 0.0), (1.0, 0.0)],
            "偏移量": 0.0,
            "频率": 1.0,
            "幅值比例": 1.0,
            "波形状态": WaveformStatus.Unset,
            "当前电机": "1号电机"
        }
        self.motor_pool = {
            "1号电机": {
                "零位": -2.0,
                "限位": 70.0
            }
        }
        self.client: Optional[ModbusTcpClient] = None
        self.thread_pool = QThreadPool.globalInstance()

        self._read_position_thread = None
        self._stop_thread_flag = Event()

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
        self.connection_status = ConnectionStatusManager(self)
        self.connection_status.connection_request.connect(self.open_connection_dialog)
        self.connection_status.disconnected.connect(self.on_plc_disconnected)
        self.status_bar.addPermanentWidget(self.connection_status)

        """
        菜单栏
        """
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        # 文件
        file_menu = QMenu("文件", self)
        menu_bar.addMenu(file_menu)

        read_waveform_action = QAction("读取波形文件", self)
        read_waveform_action.triggered.connect(self.read_waveform_file)
        file_menu.addAction(read_waveform_action)

        save_waveform_action = QAction("保存波形文件", self)
        save_waveform_action.triggered.connect(self.save_waveform_file)
        file_menu.addAction(save_waveform_action)

        export_mock_waveform_action = QAction("导出虚拟波形", self)
        export_mock_waveform_action.triggered.connect(self.export_mock_waveform)
        file_menu.addAction(export_mock_waveform_action)

        """
        上区域 - 左布局
        """
        left_layout = QVBoxLayout()

        # 波形调制区域
        self.waveform_modulator = WaveformModulator(self.config)
        self.waveform_modulator.points_changed.connect(lambda: (
            self.latex_board.create_polynomial_task(self.config["插值点集"]),
            self.update_status(f"正在使用{InterpolationManager.get_name(self.config["插值方法"])}插值法进行计算！"),
        ))
        self.waveform_modulator.waveform_status.connect(lambda status: (
            self.config.__setitem__("波形状态", status),
            self.update_waveform_status(status),
            self.update_mock_waveform_display(),
        ))
        left_layout.addWidget(self.waveform_modulator)

        # 波形状态区域
        self.waveform_status_board = QLabel()
        self.waveform_status_board.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_waveform_status(self.config["波形状态"])
        left_layout.addWidget(self.waveform_status_board)

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

        motor_selection_label = QLabel("选择电机：")
        motor_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_setting_layout.addWidget(motor_selection_label, 1, 0, alignment=Qt.AlignmentFlag.AlignCenter)

        self.motor_selection_box = QComboBox()
        self.motor_selection_box.addItems(list(self.motor_pool.keys()))
        self.motor_selection_box.currentTextChanged.connect(lambda name: (
            self.config.__setitem__("当前电机", name)
        ))
        motor_setting_layout.addWidget(self.motor_selection_box, 1, 1)

        zero_position_label = QLabel("零位：")
        zero_position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_setting_layout.addWidget(zero_position_label, 2, 0, alignment=Qt.AlignmentFlag.AlignCenter)

        self.zero_position = QDoubleSpinBox()
        self.zero_position.setRange(-10, 1000)
        self.zero_position.setDecimals(1)
        self.zero_position.setSingleStep(0.1)
        self.zero_position.setValue(-2)
        self.zero_position.setSuffix(" mm")
        self.zero_position.valueChanged.connect(lambda zero: (
            self.motor_pool[self.config["当前电机"]].__setitem__("零位", zero),
            self.mock_chart.axis_y.setMin(zero),
        ))
        motor_setting_layout.addWidget(self.zero_position, 2, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        limit_position_label = QLabel("限位：")
        limit_position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_setting_layout.addWidget(limit_position_label, 3, 0, alignment=Qt.AlignmentFlag.AlignCenter)

        self.limit_position = QDoubleSpinBox()
        self.limit_position.setRange(0, 1000)
        self.limit_position.setDecimals(1)
        self.limit_position.setSingleStep(0.1)
        self.limit_position.setValue(100)
        self.limit_position.setSuffix(" mm")
        self.limit_position.valueChanged.connect(lambda limit: (
            self.motor_pool[self.config["当前电机"]].__setitem__("限位", limit),
            self.set_offset.setMaximum(limit),
            self.mock_chart.axis_y.setMax(limit),
        ))
        motor_setting_layout.addWidget(self.limit_position, 3, 1)

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

        self.method_selection = QComboBox()
        self.method_selection.addItems([InterpolationManager.get_name(method) for method in Interpolation])
        self.method_selection.currentTextChanged.connect(lambda text: (
            self.config.__setitem__("插值方法", Interpolation[text]),
            self.waveform_modulator.update(),
            self.waveform_modulator.calc_polynomial()
        ))
        params_layout.addWidget(self.method_selection, 1, 1)

        self.set_offset = QDoubleSpinBox()
        self.set_offset.setRange(self.motor_pool[self.config["当前电机"]]["零位"],
                                 self.motor_pool[self.config["当前电机"]]["限位"])
        self.set_offset.setDecimals(1)
        self.set_offset.setSingleStep(0.1)
        self.set_offset.setValue(self.config["偏移量"])
        self.set_offset.setSuffix(" mm")
        self.set_offset.valueChanged.connect(lambda value: (
            self.config.__setitem__("偏移量", value),
            self.update_mock_waveform_display(),
        ))
        params_layout.addWidget(QLabel("偏移量："), 2, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        params_layout.addWidget(self.set_offset, 2, 1)

        self.set_frequency = QDoubleSpinBox()
        self.set_frequency.setDecimals(1)
        self.set_frequency.setSingleStep(0.1)
        self.set_frequency.setValue(self.config["频率"])
        self.set_frequency.setSuffix(" Hz")
        self.set_frequency.valueChanged.connect(lambda value: (
            self.config.__setitem__("频率", value),
            self.update_mock_waveform_display(),
        ))
        params_layout.addWidget(QLabel("频率："), 3, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        params_layout.addWidget(self.set_frequency, 3, 1)

        self.set_amplitude = QSpinBox()
        self.set_amplitude.setRange(0, 1000)
        self.set_amplitude.setSingleStep(1)
        self.set_amplitude.setValue(int(self.config["幅值比例"] * 100))
        self.set_amplitude.setSuffix(" %")
        self.set_amplitude.valueChanged.connect(lambda value: (
            self.config.__setitem__("幅值比例", float(value) / 100),
            self.update_mock_waveform_display(),
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

        self.motor_status_light = StatusLight()
        motor_init_layout.addWidget(self.motor_status_light, 1, 0, 2, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        self.power_button = QPushButton()
        self.power_button.setText(MotorPowerStatus.PowerOn)
        self.power_button.clicked.connect(self.toggle_motor_power)
        motor_init_layout.addWidget(self.power_button, 1, 1)

        self.reset_button = QPushButton()
        self.reset_button.setText("复位")
        self.reset_button.clicked.connect(self.motor_reset)
        motor_init_layout.addWidget(self.reset_button, 2, 1)

        self.move_to_target_button = QPushButton()
        self.move_to_target_button.setText("移动至")
        self.move_to_target_button.clicked.connect(self.motor_move_to_target)
        motor_init_layout.addWidget(self.move_to_target_button, 3, 0)

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

        simulation_time_label = QLabel("模拟时长：")
        simulation_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_running_layout.addWidget(simulation_time_label, 1, 0, alignment=Qt.AlignmentFlag.AlignCenter)

        simulation_time = QDoubleSpinBox()
        simulation_time.setRange(0, 100)
        simulation_time.setDecimals(1)
        simulation_time.setSingleStep(0.1)
        simulation_time.setValue(1.0)
        simulation_time.setSuffix(" s")
        simulation_time.valueChanged.connect(lambda value: (
            self.mock_chart.axis_x.setMax(value),
            self.update_mock_waveform_display(),
        ))
        motor_running_layout.addWidget(simulation_time, 1, 1)

        self.start_close_button = QPushButton()
        self.start_close_button.setText(MotorOperationStatus.Start)
        self.start_close_button.setStyleSheet("QPushButton { height: 2.5em; } ")
        self.start_close_button.clicked.connect(self.toggle_motor_operation)
        motor_running_layout.addWidget(self.start_close_button, 2, 0, 2, 2)

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

        feedback_sub_layout = QHBoxLayout()

        self.record_status_manager = RecordStatusManager(self)
        self.record_status_manager.status_changed.connect(
            lambda status: self.feedback_chart.toggle_record_status(status))
        feedback_sub_layout.addWidget(self.record_status_manager)

        scale_slider = QSlider(Qt.Orientation.Horizontal)
        scale_slider.setRange(10, 1000)
        scale_slider.setValue(100)
        scale_slider.valueChanged.connect(lambda value: self.feedback_chart.adjust_display_scope(value))
        feedback_sub_layout.addWidget(QLabel("波形比例尺："))
        feedback_sub_layout.addWidget(scale_slider)

        feedback_layout.addLayout(feedback_sub_layout)

        self.feedback_chart = FeedbackWaveformChart()
        feedback_layout.addWidget(self.feedback_chart)

        multi_widget_area.addTab(feedback_area, "反馈波形")

        # 模拟波形页
        self.mock_chart = MockWaveformChart(
            self.config, self.motor_pool,
            (self.motor_pool[self.config["当前电机"]]["零位"], self.motor_pool[self.config["当前电机"]]["限位"]))
        multi_widget_area.addTab(self.mock_chart, "模拟波形")

        # 多项式页
        self.latex_board = LatexBoard(self.config)
        self.latex_board.status_message.connect(self.update_status)
        multi_widget_area.addTab(self.latex_board, "多项式")

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
    def update_waveform_status(self, status: WaveformStatus):
        """
        更新波形状态功能实现
        :param status: 波形状态
        """
        if status == WaveformStatus.Unset:
            self.waveform_status_board.setText("当前未设置波形！")
            self.waveform_status_board.setStyleSheet(
                '''
                background-color: orange;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding-top: 5px;
                padding-bottom: 5px;
                '''
            )
        elif status == WaveformStatus.Normal:
            self.waveform_status_board.setText("波形正常，可以执行！")
            self.waveform_status_board.setStyleSheet(
                '''
                background-color: green;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding-top: 5px;
                padding-bottom: 5px;
                '''
            )
        elif status == WaveformStatus.Abnormal:
            self.waveform_status_board.setText("波形异常，无法执行！")
            self.waveform_status_board.setStyleSheet(
                '''
                background-color: red;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding-top: 5px;
                padding-bottom: 5px;
                '''
            )
        else:
            raise ValueError("未知的波形状态！")

    @Slot()
    def toggle_motor_power(self):
        """
        电机通电/断电
        """
        if not check_client_status(self.client):
            QMessageBox.critical(self, "错误", "当前与PLC通讯异常，请检查！")
            return

        sender = self.sender()
        if sender.text() == MotorPowerStatus.PowerOn:
            process_response(self.client.write_register(RegisterAddress.Power, 1))
            self.motor_status_light.setStatus(StatusLight.Color.Green)
            sender.setText(MotorPowerStatus.PowerOff)
        elif sender.text() == MotorPowerStatus.PowerOff:
            if self.start_close_button.text() == MotorOperationStatus.Stop:
                if (QMessageBox.warning(self, "警告", "当前电机正在运行，确定要断电吗？",
                                        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                        == QMessageBox.StandardButton.Cancel):
                    return
                self.start_close_button.clicked.emit()
            process_response(self.client.write_register(RegisterAddress.Power, 0))
            self.motor_status_light.setStatus(StatusLight.Color.Red)
            sender.setText(MotorPowerStatus.PowerOn)
        else:
            raise ValueError("错误的电机电源状态！")

    @Slot()
    def motor_reset(self):
        """
        电机复位
        """
        if not check_client_status(self.client):
            QMessageBox.critical(self, "错误", "当前与PLC通讯异常，请检查！")
            return

        process_response(self.client.write_registers(RegisterAddress.ErrorCode, [0]))
        self.update_status("电机错误状态已清除！")

    @Slot()
    def motor_move_to_target(self):
        """
        电机移动至目标
        """
        if not check_client_status(self.client):
            QMessageBox.critical(self, "错误", "当前与PLC通讯异常，请检查！")
            return

    @Slot()
    def toggle_motor_operation(self):
        """
        电机开始运行/停止运行
        """
        sender = self.sender()

        # 开始运行
        if sender.text() == MotorOperationStatus.Start:
            if not check_client_status(self.client):
                QMessageBox.critical(self, "错误", "当前与PLC通讯异常，请检查！")
                return

            if self.config.get("波形状态") == WaveformStatus.Abnormal:
                QMessageBox.critical(self, "错误", "波形异常，无法设置参数，请检查！")
                return
            elif self.config.get("波形状态") == WaveformStatus.Unset:
                QMessageBox.critical(self, "错误", "当前未设置波形，请先设置波形！")
                return

            if self.client.read_holding_registers(RegisterAddress.ErrorCode).registers[0] != 0:
                QMessageBox.critical(self, "错误", "当前PLC故障，请先复位后再开始！")
                return

            if self.client.read_holding_registers(RegisterAddress.Power).registers[0] != 1:
                QMessageBox.critical(self, "错误", "当前电机未启动，请先将启动后再开始！")
                return

            model = self.latex_board.model
            motor = self.motor_pool[self.config["当前电机"]]
            zero_pos, limit_pos = motor["零位"], motor["限位"]
            freq, scale, offset = self.config["频率"], self.config["幅值比例"], self.config["偏移量"]

            combined_scale = (limit_pos - zero_pos) * scale
            combined_offset = (-zero_pos * scale) + offset  # 合并偏移
            coefficient_matrix = model.c.T.copy()
            coefficient_matrix[:, :3] *= combined_scale
            coefficient_matrix[:, 3] = (coefficient_matrix[:, 3] * combined_scale) + combined_offset

            encoded_frequency = float_to_fixed(np.array([freq]))
            encoded_coefficients = float_to_fixed(
                np.append(np.column_stack([model.x[:-1], coefficient_matrix]).flatten(), 1))
            packet = np.concatenate((encoded_frequency, np.array([len(model.x) - 1]), encoded_coefficients))

            address = RegisterAddress.Frequency
            split_packet = split_array(packet)
            for sub_packet in split_packet:
                process_response(self.client.write_registers(address, sub_packet))
                address += len(sub_packet)

            process_response(self.client.write_registers(RegisterAddress.Status, [2]))

            self._read_position_thread = Thread(target=self._read_position, daemon=True)
            self._stop_thread_flag.clear()
            self._read_position_thread.start()

            self.update_status("运行参数设置成功，电机开始运行！")
            sender.setText(MotorOperationStatus.Stop)

        # 停止运行
        elif sender.text() == MotorOperationStatus.Stop:
            try:
                process_response(self.client.write_registers(0x6000, [0]))
            except ConnectionResetError:
                pass

            self._stop_thread_flag.set()

            self.update_status("电机停止运行！")
            sender.setText(MotorOperationStatus.Start)

        else:
            raise ValueError("错误的电机运行状态！")

    def _read_position(self):
        """
        读取电机位置
        """
        while not self._stop_thread_flag.is_set():
            position = fixed_to_float(np.array(
                self.client.read_holding_registers(RegisterAddress.Position, count=2).registers)).item()
            self.feedback_chart.add_point(position)

    @Slot()
    def read_waveform_file(self):
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
                        self.method_selection.setCurrentText(self.config["插值方法"].value)
                        self.set_offset.setValue(self.config["偏移量"])
                        self.set_frequency.setValue(self.config["频率"])
                        self.set_amplitude.setValue(int(self.config["幅值比例"] * 100))
                        self.waveform_modulator.update()
                        self.waveform_modulator.points_changed.emit()  # 发射信号触发公式绘制
                    self.update_status(f"成功从 {normalized_path} 读取波形数据！")
                except Exception as e:
                    QMessageBox.critical(self, "警告", f"读取波形数据出错: {e}")

    @Slot()
    def save_waveform_file(self):
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
    def open_connection_dialog(self):
        """
        打开连接窗口
        """
        dialog = ConnectionDialog(self)
        dialog.status.connect(self.connection_status.set_status)
        dialog.connection_request.connect(self.create_connection_request)
        dialog.exec()

    @Slot(str, int)
    def create_connection_request(self, host: str, port: int):
        """
        新建PLC连接请求
        :param host: 目标IP地址
        :param port: 目标端口
        """
        task = ConnectionTask(host, port)
        task.connect_result.connect(self.process_connection_result)
        self.thread_pool.start(TaskRunner(task))

    @Slot(ModbusTcpClient)
    def process_connection_result(self, client: ModbusTcpClient):
        """
        处理PLC连接响应
        :param client: ModbusTCP客户端对象
        """
        self.client = client
        if client is None:
            self.connection_status.set_status(ConnectionStatus.Disconnected)
        else:
            self.connection_status.set_status(ConnectionStatus.Connected)
            if self.client.read_holding_registers(RegisterAddress.Power, count=1).registers[0] == 1:
                self.motor_status_light.setStatus(StatusLight.Color.Green)
            else:
                self.motor_status_light.setStatus(StatusLight.Color.Grey)

    @Slot()
    def update_mock_waveform_display(self):
        """
        更新虚拟波形功能实现
        """
        self.mock_chart.update_data(self.waveform_modulator.interpolated_points)

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
                    for x, y in self.waveform_modulator.interpolated_points:
                        # X坐标变换
                        processed_x = x / self.config.get("频率")

                        # Y坐标变换
                        absolute_y = y * self.motor_pool.get(self.motor_selection_box.currentText()).get("导轨长度")  # 换算绝对坐标
                        processed_y = (absolute_y * self.config.get("幅值比例")) + self.config.get("偏移量")  # 偏移和增幅

                        result.append(
                            (processed_x, max(self.mock_chart.axis_y.min(), min(processed_y, self.mock_chart.axis_y.max()))))

                    df = pd.DataFrame(result, columns=['x', 'y'])
                    df.astype({'x': 'float32', 'y': 'float32'}).to_csv(
                        normalized_path,
                        index=False,
                        float_format='%.4f'  # 统一小数位数
                    )
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"导出虚拟波形时出错: {e}！")

    @Slot()
    def on_plc_disconnected(self):
        """
        PLC连接断开处理
        """
        self.motor_status_light.setStatus(StatusLight.Color.Grey)
        if self.start_close_button.text() == MotorOperationStatus.Stop:
            self.start_close_button.clicked.emit()


if __name__ == "__main__":
    mathjax = Process(target=run_server, daemon=True)
    mathjax.start()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
