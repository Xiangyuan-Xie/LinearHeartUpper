import re

from PySide6.QtCore import Signal, Slot, QThreadPool
from PySide6.QtWidgets import QDialog, QGridLayout, QLabel, QLineEdit, QPushButton, QMessageBox

from common import ConnectionStatus


class ConnectionDialog(QDialog):
    status = Signal(ConnectionStatus)
    connection_request = Signal(str, int)
    thread_pool = QThreadPool.globalInstance()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("连接")

        self.layout = QGridLayout(self)

        host_label = QLabel("目标地址：")
        self.layout.addWidget(host_label, 1, 0)

        self.host = QLineEdit("192.168.0.100")
        self.layout.addWidget(self.host, 1, 1)

        port_label = QLabel("目标端口：")
        self.layout.addWidget(port_label, 2, 0)

        self.port = QLineEdit("502")
        self.layout.addWidget(self.port, 2, 1)

        self.communication_button = QPushButton("连接")
        self.communication_button.clicked.connect(self._connect_plc)
        self.layout.addWidget(self.communication_button, 3, 0, 1, 2)

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

        self.status.emit(ConnectionStatus.Connecting)
        self.connection_request.emit(self.host.text(), int(self.port.text()))

        self.accept()
