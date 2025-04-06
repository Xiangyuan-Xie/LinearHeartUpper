from enum import StrEnum

from PySide6.QtCore import Signal, QTimer, Qt, Slot
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QMessageBox

from common import ConnectionStatus
from communication import check_client_status
from widget.status_light import StatusLight


class ConnectionStatusManager(QWidget):
    connection_request = Signal()
    disconnected = Signal()
    color_map = {
        ConnectionStatus.Disconnected: StatusLight.Color.Red,
        ConnectionStatus.Connecting: StatusLight.Color.Orange,
        ConnectionStatus.Connected: StatusLight.Color.Green,
    }

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.current_status = None

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 0, 5, 0)
        self.layout.setSpacing(8)

        self.status_light = StatusLight(12)
        self.layout.addWidget(self.status_light)

        self.status_label = QLabel(self.current_status)
        self.status_label.setStyleSheet("color: #666;")
        self.layout.addWidget(self.status_label)

        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_connection)
        self.check_timer.start(1000)

        self.set_status(ConnectionStatus.Disconnected)

    def set_status(self, status: ConnectionStatus):
        """
        设置状态
        :param status: 新状态
        """
        if status != self.current_status:
            self.current_status = status
            self.status_label.setText(status)
            self.status_light.setStatus(self.color_map[status])
            if status == ConnectionStatus.Disconnected:
                self.status_light.setFlashing(True)
            else:
                self.status_light.setFlashing(False)
            self.update()

    def check_connection(self):
        """
        检测连接状态
        """
        if self.current_status == ConnectionStatus.Connected and not check_client_status(self.parent.client):
            self.set_status(ConnectionStatus.Disconnected)
            self.disconnected.emit()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.current_status == ConnectionStatus.Disconnected:
                self.connection_request.emit()

    def enterEvent(self, event):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status_label.setStyleSheet("color: #444; text-decoration: underline;")

    def leaveEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.status_label.setStyleSheet("color: #666;")


class RecordStatusManager(QWidget):
    status_changed = Signal(bool)

    class RecordStatus(StrEnum):
        Start = "开始录制"
        Stop = "结束录制"

    def __init__(self, parent):
        super().__init__()
        self.parent = parent

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 0, 5, 0)
        self.layout.setSpacing(8)

        self.status_light = StatusLight(15)
        self.layout.addWidget(self.status_light)

        self.record_button = QPushButton(self.RecordStatus.Start)
        self.record_button.clicked.connect(self.toggle_record_status)
        self.layout.addWidget(self.record_button)

    @Slot()
    def toggle_record_status(self):
        """
        切换录制状态
        """
        if self.record_button.text() == self.RecordStatus.Start:
            if not check_client_status(self.parent.client):
                if (QMessageBox.warning(self.parent, "警告", "当前没有反馈波形，确定要继续开始录制吗？",
                                        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                        == QMessageBox.StandardButton.Cancel):
                    return
            self.status_changed.emit(True)
            self.record_button.setText(self.RecordStatus.Stop)
            self.status_light.setStatus(StatusLight.Color.Red)
        elif self.record_button.text() == self.RecordStatus.Stop:
            self.status_changed.emit(False)
            self.record_button.setText(self.RecordStatus.Start)
            self.status_light.setStatus(StatusLight.Color.Grey)
        else:
            raise ValueError("错误的波形录制状态！")