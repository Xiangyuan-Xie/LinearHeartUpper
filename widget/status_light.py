from PySide6.QtWidgets import QLabel


class StatusLight(QLabel):
    def __init__(self, color: str="red"):
        super().__init__()
        self.setFixedSize(20, 20)
        self.set_color(color)

    def set_color(self, color):
        self.setStyleSheet(f"background-color: {color}; border-radius: 10px;")