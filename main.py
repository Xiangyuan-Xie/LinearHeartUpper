import sys
import time
from datetime import datetime
from multiprocessing import Process
from threading import Thread, Event, Lock
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QThreadPool, Slot, QDir
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QMainWindow, QHBoxLayout, QComboBox, QFrame, QDoubleSpinBox,
                               QTabWidget, QMenuBar, QMenu, QFileDialog, QSpinBox, QVBoxLayout, QWidget, QLabel,
                               QGridLayout, QPushButton, QMessageBox, QSlider, QSizePolicy)
from loguru import logger
from pymodbus.client import ModbusTcpClient

from common import (Interpolation, InterpolationManager, RegisterAddress, MotorPowerStatus, MotorOperationStatus,
                    ConnectionStatus)
from communication import (float_to_fixed, split_array, process_write_response, process_status_code, fixed_to_float)
from mathjax_server import run_server
from task import ConnectionTask, TaskRunner, SaveMockwaveformTask, SaveWaveformConfigTask, ReadWaveformConfigTask
from widget.chart import FeedbackWaveformChart, MockWaveformChart
from widget.connection_dialog import ConnectionDialog
from widget.latex_board import LatexBoard
from widget.status_light import StatusLight
from widget.status_manager import ConnectionStatusManager, RecordStatusManager, MotorStatusManager
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
                "零位": 0.0,
                "限位": 20.0
            }
        }
        self.thread_pool = QThreadPool.globalInstance()

        self._mathjax_server_process = Process(target=run_server, daemon=True)
        self._mathjax_server_process.start()

        self.lock = Lock()
        self.client: Optional[ModbusTcpClient] = None
        self._status_monitor_thread: Optional[Thread] = None
        self._status_monitor_flag = Event()

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
        self.status_bar.addPermanentWidget(self.connection_status)
        self.create_connection_request('192.168.0.100', 502)

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

        # 电机设置
        motor_setting_frame = QFrame()
        motor_setting_frame.setFrameShape(QFrame.Shape.StyledPanel)
        motor_setting_frame.setFrameShadow(QFrame.Shadow.Raised)

        motor_setting_layout = QGridLayout()

        motor_setting_label = QLabel("<h3>电机设置</h3>")
        motor_setting_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_setting_layout.addWidget(motor_setting_label, 0, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter)

        motor_selection_label = QLabel("选择电机：")
        motor_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_setting_layout.addWidget(motor_selection_label, 1, 0, alignment=Qt.AlignmentFlag.AlignCenter)

        motor_selection_box = QComboBox()
        motor_selection_box.addItems(list(self.motor_pool.keys()))
        motor_selection_box.currentTextChanged.connect(lambda name: (
            self.config.__setitem__("当前电机", name)
        ))
        motor_setting_layout.addWidget(motor_selection_box, 1, 1)

        zero_position_label = QLabel("零位：")
        zero_position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_setting_layout.addWidget(zero_position_label, 2, 0, alignment=Qt.AlignmentFlag.AlignCenter)

        zero_position = QDoubleSpinBox()
        zero_position.setRange(-10, 1000)
        zero_position.setDecimals(1)
        zero_position.setSingleStep(0.1)
        zero_position.setValue(self.motor_pool[self.config["当前电机"]]["零位"])
        zero_position.setSuffix(" mm")
        zero_position.valueChanged.connect(lambda zero: (
            self.motor_pool[self.config["当前电机"]].__setitem__("零位", zero),
            self.adjust_y_scale(zero_position=zero)
        ))
        motor_setting_layout.addWidget(zero_position, 2, 1)

        limit_position_label = QLabel("限位：")
        limit_position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_setting_layout.addWidget(limit_position_label, 3, 0, alignment=Qt.AlignmentFlag.AlignCenter)

        limit_position = QDoubleSpinBox()
        limit_position.setRange(0, 1000)
        limit_position.setDecimals(1)
        limit_position.setSingleStep(0.1)
        limit_position.setValue(self.motor_pool[self.config["当前电机"]]["限位"])
        limit_position.setSuffix(" mm")
        limit_position.valueChanged.connect(lambda limit: (
            self.motor_pool[self.config["当前电机"]].__setitem__("限位", limit),
            self.adjust_y_scale(limit_position=limit)
        ))
        motor_setting_layout.addWidget(limit_position, 3, 1)

        motor_setting_frame.setLayout(motor_setting_layout)
        middle_layout.addWidget(motor_setting_frame)

        # 参数设置
        params_frame = QFrame()
        params_frame.setFrameShape(QFrame.Shape.StyledPanel)
        params_frame.setFrameShadow(QFrame.Shadow.Raised)

        params_layout = QGridLayout()

        params_label = QLabel("<h3>参数设置</h3>")
        params_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        params_layout.addWidget(params_label, 0, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter)

        set_waveform_label = QLabel("插值方法：")
        set_waveform_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        params_layout.addWidget(set_waveform_label, 1, 0, alignment=Qt.AlignmentFlag.AlignCenter)

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
        motor_init_layout.setColumnStretch(0, 1)
        motor_init_layout.setColumnStretch(1, 1)

        motor_init_label = QLabel("<h3>电机初始化</h3>")
        motor_init_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_init_layout.addWidget(motor_init_label, 0, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter)

        self.power_button = QPushButton()
        self.power_button.setText(MotorPowerStatus.PowerOn)
        self.power_button.clicked.connect(self.toggle_motor_power)
        motor_init_layout.addWidget(self.power_button, 1, 0)

        reset_button = QPushButton()
        reset_button.setText("复位")
        reset_button.clicked.connect(self.motor_reset)
        motor_init_layout.addWidget(reset_button, 1, 1)

        self.move_to_target_button = QPushButton()
        self.move_to_target_button.setText("移动至")
        self.move_to_target_button.clicked.connect(self.motor_move_to_target)
        motor_init_layout.addWidget(self.move_to_target_button, 2, 0)

        self.set_movement_distance = QDoubleSpinBox()
        self.set_movement_distance.setDecimals(1)
        self.set_movement_distance.setSingleStep(0.1)
        self.set_movement_distance.setValue(0)
        self.set_movement_distance.setSuffix(" mm")
        motor_init_layout.addWidget(self.set_movement_distance, 2, 1)

        simulation_time_label = QLabel("模拟时长：")
        simulation_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_init_layout.addWidget(simulation_time_label, 3, 0, alignment=Qt.AlignmentFlag.AlignCenter)

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
        motor_init_layout.addWidget(simulation_time, 3, 1)

        motor_init_frame.setLayout(motor_init_layout)
        right_layout.addWidget(motor_init_frame)

        # 电机运行
        motor_running_frame = QFrame()
        motor_running_frame.setFrameShape(QFrame.Shape.StyledPanel)
        motor_running_frame.setFrameShadow(QFrame.Shadow.Raised)

        motor_running_layout = QGridLayout()

        motor_running_label = QLabel("<h3>电机运行</h3>")
        motor_running_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motor_running_layout.addWidget(motor_running_label, 0, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter)

        self.motor_status_manager = MotorStatusManager()
        motor_running_layout.addWidget(self.motor_status_manager, 1, 0, 2, 2)

        self.start_close_button = QPushButton()
        self.start_close_button.setText(MotorOperationStatus.Start)
        self.start_close_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.start_close_button.clicked.connect(self.toggle_motor_operation)
        motor_running_layout.addWidget(self.start_close_button, 3, 0, 2, 2)

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

        self.record_status_manager = RecordStatusManager(self, self.connection_status)
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

        self.feedback_chart = FeedbackWaveformChart((self.motor_pool[self.config["当前电机"]]["零位"],
                                                     self.motor_pool[self.config["当前电机"]]["限位"]))
        self.feedback_chart.status_message.connect(self.update_status)
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
        sender = self.sender()
        if sender.text() == MotorPowerStatus.PowerOn:
            if self.motor_status_manager.get_color() == StatusLight.Color.Red:
                QMessageBox.critical(self, "错误", "当前电机存在故障，请复位后再开始任务！")
                return

            if not process_write_response(
                    self.client.write_coil(RegisterAddress.Coil.PowerOn, True), "保持寄存器"):
                QMessageBox.warning(self, "警告", "与PLC通讯时发生错误，请检查！")
                return
            time.sleep(0.05)
            process_write_response(
                self.client.write_coil(RegisterAddress.Coil.PowerOn, False), "保持寄存器")
            sender.setText(MotorPowerStatus.PowerOff)
        elif sender.text() == MotorPowerStatus.PowerOff:
            if not process_write_response(
                    self.client.write_coil(RegisterAddress.Coil.PowerOff, True), "保持寄存器"):
                QMessageBox.warning(self, "警告", "与PLC通讯时发生错误，请检查！")
                return
            time.sleep(0.05)
            process_write_response(self.client.write_coil(RegisterAddress.Coil.PowerOff, False), "保持寄存器")
            if self.start_close_button.text() == MotorOperationStatus.Stop:  # 运行时断电处理
                self.start_close_button.setText(MotorOperationStatus.Start)
            sender.setText(MotorPowerStatus.PowerOn)
        else:
            raise ValueError("错误的电源状态！")

    @Slot()
    def motor_reset(self):
        """
        电机复位
        """
        if not process_write_response(self.client.write_coil(RegisterAddress.Coil.Reset, True), "线圈"):
            QMessageBox.warning(self, "警告", "与PLC通讯时发生错误，请检查！")
            return
        time.sleep(0.05)
        process_write_response(self.client.write_coil(RegisterAddress.Coil.Reset, False), "线圈")

    @Slot()
    def motor_move_to_target(self):
        """
        电机移动至目标
        """
        status_color = self.motor_status_manager.get_color()
        if status_color == StatusLight.Color.Orange:
            QMessageBox.critical(self, "错误", "当前电机正在工作，请等待电机空闲再开始任务！")
            return
        elif status_color == StatusLight.Color.Red:
            QMessageBox.critical(self, "错误", "当前电机存在故障，请复位后再开始任务！")
            return
        elif status_color == StatusLight.Color.Grey:
            QMessageBox.critical(self, "错误", "当前电机离线，请启动电机后再开始任务！")
            return

        packet = float_to_fixed(np.array([self.set_movement_distance.value()]), byte_order='>')
        if not process_write_response(
                self.client.write_registers(RegisterAddress.Holding.TargetPos, packet.tolist()), "线圈"):
            QMessageBox.warning(self, "警告", "与PLC通讯时发生错误，请检查！")
            return

        if not process_write_response(
                self.client.write_coil(RegisterAddress.Coil.isWriteTarget, True), "线圈"):
            QMessageBox.warning(self, "警告", "与PLC通讯时发生错误，请检查！")
            return
        time.sleep(0.05)
        process_write_response(
            self.client.write_coil(RegisterAddress.Coil.isWriteTarget, False), "线圈")

    @Slot()
    def toggle_motor_operation(self):
        """
        电机开始运行/停止运行
        """
        sender = self.sender()

        # 开始运行
        if sender.text() == MotorOperationStatus.Start:
            if self.config.get("波形状态") == WaveformStatus.Abnormal:
                QMessageBox.critical(self, "错误", "波形异常，无法设置参数，请检查！")
                return
            elif self.config.get("波形状态") == WaveformStatus.Unset:
                QMessageBox.critical(self, "错误", "当前未设置波形，请先设置波形！")
                return

            status_color = self.motor_status_manager.get_color()
            if status_color == StatusLight.Color.Orange:
                QMessageBox.critical(self, "错误", "当前电机正在工作，请等待电机空闲再开始任务！")
                return
            elif status_color == StatusLight.Color.Red:
                QMessageBox.critical(self, "错误", "当前电机存在未复位的错误，请复位后再开始任务！")
                return
            elif status_color == StatusLight.Color.Grey:
                QMessageBox.critical(self, "错误", "当前电机离线，请启动电机后再开始任务！")
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

            encoded_frequency = float_to_fixed(np.array([freq]), byte_order='>')
            encoded_coefficients = float_to_fixed(
                np.append(np.column_stack([model.x[:-1], coefficient_matrix]).flatten(), 1))
            packet = np.concatenate((np.array([len(model.x) - 1]), encoded_frequency, encoded_coefficients))

            address = RegisterAddress.Holding.NumberOfInterval
            split_packet = split_array(packet)
            for sub_packet in split_packet:
                if not process_write_response(
                        self.client.write_registers(address, sub_packet), "保持寄存器"):
                    QMessageBox.warning(self, "警告", "与PLC通讯时发生错误，请检查！")
                    return
                address += len(sub_packet)

            if not process_write_response(
                    self.client.write_coil(RegisterAddress.Coil.isWriteCoefficients, True), "线圈"):
                QMessageBox.warning(self, "警告", "与PLC通讯时发生错误，请检查！")
                return
            time.sleep(0.05)
            process_write_response(
                self.client.write_coil(RegisterAddress.Coil.isWriteCoefficients, False), "线圈")

            if not process_write_response(
                    self.client.write_coil(RegisterAddress.Coil.Start, True), "线圈"):
                QMessageBox.warning(self, "警告", "与PLC通讯时发生错误，请检查！")
                return
            time.sleep(0.05)
            process_write_response(
                self.client.write_coil(RegisterAddress.Coil.Start, False), "线圈")

            self.update_status("运行参数设置成功，电机开始运行！")
            sender.setText(MotorOperationStatus.Stop)

        # 停止运行
        elif sender.text() == MotorOperationStatus.Stop:
            if not process_write_response(
                    self.client.write_coil(RegisterAddress.Coil.Stop, True), "线圈"):
                QMessageBox.warning(self, "警告", "与PLC通讯时发生错误，请检查！")
                return
            time.sleep(0.05)
            process_write_response(
                self.client.write_coil(RegisterAddress.Coil.Stop, False), "线圈")
            self.update_status("电机已停止运行！")
            sender.setText(MotorOperationStatus.Start)

        else:
            raise ValueError("错误的电机运行状态！")

    @Slot()
    def read_waveform_file(self):
        """
        从文件中读取波形数据功能实现
        """
        path, _ = QFileDialog.getOpenFileName(
            parent=self,
            caption="读取波形",
            filter="DAT Files (*.dat);;All Files (*)",
            selectedFilter="DAT Files (*.dat)",
            options=QFileDialog.Option.ReadOnly
        )
        if path:
            task = ReadWaveformConfigTask(path)
            task.status_message.connect(self.update_status)
            task.result.connect(self.on_read_waveform_file_done)
            self.thread_pool.start(TaskRunner(task))

    @Slot(dict)
    def on_read_waveform_file_done(self, config: dict, path: str):
        """
        处理波形文件读取任务的结果
        :param config: 读取的配置文件
        :param path: 读取的路径
        """
        self.config.update(config)
        self.method_selection.setCurrentIndex(self.config["插值方法"].value)
        self.set_offset.setValue(self.config["偏移量"])
        self.set_frequency.setValue(self.config["频率"])
        self.set_amplitude.setValue(int(self.config["幅值比例"] * 100))
        self.waveform_modulator.update()
        self.waveform_modulator.points_changed.emit()
        self.update_status(f"成功从 {QDir.toNativeSeparators(path)} 读取波形数据！")

    @Slot()
    def save_waveform_file(self):
        """
        保存波形数据到文件功能实现
        """
        path, _ = QFileDialog.getSaveFileName(
            parent=self,
            caption="保存波形",
            filter="DAT Files (*.dat);;All Files (*)",
            selectedFilter="DAT Files (*.dat)",
            options=QFileDialog.Option.ReadOnly
        )
        if path:
            task = SaveWaveformConfigTask(path, self.config)
            task.status_message.connect(self.update_status)
            self.thread_pool.start(TaskRunner(task))

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
        logger.info(f"发送PLC连接请求，目标：{host}:{port}")

    @Slot(ModbusTcpClient)
    def process_connection_result(self, client: ModbusTcpClient):
        """
        处理PLC连接响应
        :param client: ModbusTCP客户端对象
        """
        self.client = client
        if client is None:
            self.connection_status.set_status(ConnectionStatus.Disconnected)
            logger.info("PLC连接失败！")
        else:
            self.connection_status.set_status(ConnectionStatus.Connected)
            logger.info("PLC连接成功！")

            # 连接后首先检查一次
            response = self.client.read_input_registers(RegisterAddress.Input.Status, count=1)
            if response and not response.isError():
                color, message = process_status_code(response.registers[0])
                self.motor_status_manager.set_status(color, message)

            # 释放线程持续读取电机状态
            if self._status_monitor_thread is not None and self._status_monitor_thread.is_alive():
                self._status_monitor_flag.set()
                logger.info("存在旧的状态检测线程，等待结束...")
                self._status_monitor_thread.join()
            self._status_monitor_flag.clear()
            self._status_monitor_thread = Thread(target=self._status_monitor, daemon=True)
            self._status_monitor_thread.start()
            logger.info("状态检测线程已开启!")

    def _status_monitor(self):
        """
        状态监测线程函数
        """
        fail_count = 0
        buffer_size = 1000
        while not self._status_monitor_flag.is_set():
            time.sleep(0.1)

            # 状态字
            status_response = self.client.read_input_registers(RegisterAddress.Input.Status, count=1)
            if status_response and not status_response.isError():
                color, message = process_status_code(status_response.registers[0])
                self.motor_status_manager.set_status(color, message)
                if status_response.registers[0] == 5:
                    self.start_close_button.setText(MotorOperationStatus.Stop)
                fail_count = 0
            else:
                fail_count += 1

            # 实时位置反馈
            header_response = self.client.read_input_registers(RegisterAddress.Input.Header, count=2)
            if header_response and not header_response.isError():
                header = header_response.registers[0]
                tailer = header_response.registers[1]
                counter = (header - tailer + buffer_size) % buffer_size
                if counter <= 0:
                    continue

                encoded_position = []
                remaining = counter
                while remaining > 0:
                    read_length = min(60, remaining)
                    current_address = (tailer + (counter - remaining)) % buffer_size
                    if current_address + read_length > buffer_size:
                        first_segment = buffer_size - current_address
                        pos_response1 = self.client.read_input_registers(
                            RegisterAddress.Input.Position_Start + 2 * current_address, count=2 * first_segment)
                        pos_response2 = self.client.read_input_registers(
                            RegisterAddress.Input.Position_Start, count= 2 * (read_length - first_segment))
                        encoded_position.extend(pos_response1.registers + pos_response2.registers)
                    else:
                        pos_response = self.client.read_input_registers(
                            RegisterAddress.Input.Position_Start + 2 * current_address, count=2 * read_length)
                        encoded_position.extend(pos_response.registers)
                    remaining -= read_length

                tail_response = self.client.write_registers(RegisterAddress.Holding.Tailer, [header])
                if tail_response and not tail_response.isError():
                    decoded_position = fixed_to_float(np.array(encoded_position))
                    self.feedback_chart.add_points(decoded_position.tolist())
                fail_count = 0
            else:
                fail_count += 1
                if fail_count > 10:
                    QMessageBox.critical(self, "错误", "与PLC的通信连接已断开，请检查！")
                    logger.error("PLC通信连接异常断开！")
                    self.connection_status.set_status(ConnectionStatus.Disconnected)
                    self.motor_status_manager.set_status(StatusLight.Color.Grey, "离线")
                    if self.power_button.text() == MotorPowerStatus.PowerOff:  # 断连时电机还在通电
                        self.power_button.setText(MotorPowerStatus.PowerOn)
                    return

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
        path, _ = QFileDialog.getSaveFileName(
            parent=self,
            caption="导出虚拟波形",
            filter="CSV Files (*.csv);;All Files (*)",
            selectedFilter="CSV Files (*.csv)",
            options=QFileDialog.Option.ReadOnly
        )
        if path:
            task = SaveMockwaveformTask(
                QDir.toNativeSeparators(path),
                self.motor_pool, self.config,
                self.mock_chart.axis_y.max(),
                self.mock_chart.axis_y.min(),
                self.waveform_modulator.interpolated_points
            )
            task.status_message.connect(self.update_status)
            self.thread_pool.start(TaskRunner(task))

    def adjust_y_scale(self, zero_position: float=None, limit_position: float=None):
        """
        波形视图坐标轴自适应
        :param zero_position: 导轨零位
        :param limit_position: 导轨限位
        """
        if zero_position is None:
            zero_position = self.motor_pool[self.config["当前电机"]]["零位"]
        if limit_position is None:
            limit_position = self.motor_pool[self.config["当前电机"]]["限位"]

        self.feedback_chart.adjust_y_scale(zero_position, limit_position)
        self.mock_chart.adjust_y_scale(zero_position, limit_position)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
