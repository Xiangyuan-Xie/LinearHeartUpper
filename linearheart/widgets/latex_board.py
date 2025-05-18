from typing import Any, Dict, Sequence, Tuple

from PySide6.QtCore import QThreadPool, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from linearheart.utils.task import ExpressionTask, TaskRunner


class LatexBoard(QWidget):
    status_message = Signal(str)
    thread_pool = QThreadPool().globalInstance()

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config

        self.model = None  # 插值模型

        layout = QVBoxLayout()

        # 浏览器
        self.webview = QWebEngineView()
        self.webview.setHtml(self.generate_html_context(""))
        layout.addWidget(self.webview)

        self.setLayout(layout)

    @Slot(list)
    def create_polynomial_task(self, points: Sequence[Tuple[float, float]]):
        """
        新建多项式计算任务功能实现
        :param points: 插值点集
        """
        task = ExpressionTask(points, self.config["偏移量"], self.config["幅值比例"], self.config["插值方法"])
        task.result.connect(self._on_polynomial_result_ready)
        self.thread_pool.start(TaskRunner(task))

    @Slot(Any, str, str)
    def _on_polynomial_result_ready(self, model, polynomial: str, status: str):
        """
        插值多项式计算结果显示功能实现
        :param model: 插值模型
        :param polynomial: Latex多项式
        """
        self.model = model

        html_context = self.generate_html_context(polynomial)
        self.webview.setHtml(html_context)

        self.status_message.emit(status)

    @staticmethod
    def generate_html_context(latex_polynomial: str) -> str:
        return (
            r"""
            <!DOCTYPE html>
            <html lang="en">
                <head>
                    <script id="MathJax-script" async src="http://localhost:5000/mathjax/es5/tex-mml-chtml.js"></script>
                    <style>
                        p {
                            text-align:center;
                        }
                    </style>
                </head>
                <body>
                    <p>
        """
            + latex_polynomial
            + r"""
                    </p>
                </body>
            </html>
        """
        )
