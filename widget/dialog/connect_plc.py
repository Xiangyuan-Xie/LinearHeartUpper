import re

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QDialog, QGridLayout, QLabel, QLineEdit, QPushButton, QMessageBox


class ConnectDialog(QDialog):
    status_message = Signal(str)
    connection_info = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("设置")

        layout = QGridLayout()

        host_label = QLabel("IP地址：")
        host_label.setFixedWidth(60)
        layout.addWidget(host_label, 1, 0)

        self.host = QLineEdit("127.0.0.1")
        self.host.setFixedWidth(110)
        layout.addWidget(self.host, 1, 1)

        port_label = QLabel("端口：")
        port_label.setFixedWidth(60)
        layout.addWidget(port_label, 2, 0)

        self.port = QLineEdit("502")
        self.port.setFixedWidth(110)
        layout.addWidget(self.port, 2, 1)

        self.communication_button = QPushButton("连接")
        self.communication_button.clicked.connect(self._connect_plc)
        layout.addWidget(self.communication_button, 3, 0, 1, 2)

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
        self.accept()
        self.status_message.emit(f"正在连接PLC（{host}:{port}），请等待！")
        self.connection_info.emit(host, port)