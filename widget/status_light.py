from enum import Enum

from PySide6.QtCore import Qt, QTimer, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QBrush
from PySide6.QtWidgets import QWidget


class StatusLight(QWidget):
    class Color(Enum):
        Grey = QColor(170, 170, 170)
        Green = QColor(0, 255, 0)
        Orange = QColor(255, 165, 0)
        Red = QColor(255, 0, 0)

    def __init__(self, diameter: int=25, color: Color=Color.Grey, flashing: bool=False):
        super().__init__()
        self.diameter = diameter  # 直径
        self.current_color = color  # 颜色
        self.flashing = flashing  # 闪烁状态
        self.flash_phase = 0  # 闪烁相位

        # 动画定时器
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_animation)

    def setStatus(self, status: Color):
        """
        设置状态（颜色）
        :param status: 新状态
        """
        self.current_color = status
        self.update()

    def setFlashing(self, enable: bool):
        """
        启用/禁用闪烁效果
        :param enable: 新状态
        """
        self.flashing = enable
        self.flash_phase = 0
        self.update_timer_state()

    def update_timer_state(self):
        """
        更新定时器状态
        """
        if self.flashing and not self.animation_timer.isActive():
            self.animation_timer.start(50)
        else:
            self.animation_timer.stop()

    def update_animation(self):
        """
        更新动画
        """
        if self.flashing:
            self.flash_phase = (self.flash_phase + 1) % 20
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 计算绘制区域
        margin = (min(self.width(), self.height()) - self.diameter) / 2
        rect = QRectF(margin, margin, self.diameter, self.diameter)

        # 闪烁效果计算
        if self.flashing:
            alpha = 255 - abs(self.flash_phase - 10) * 25
            color = QColor(self.current_color.value)
            color.setAlpha(alpha)
        else:
            color = self.current_color.value

        # 绘制背景
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(rect)

    def sizeHint(self):
        return QSize(*self.minimumSizeHint().toTuple())

    def minimumSizeHint(self):
        return QSize(self.diameter + 4, self.diameter + 4)
