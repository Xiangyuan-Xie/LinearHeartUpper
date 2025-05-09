import logging

from flask import Flask
from flask_cors import CORS


def run_server():
    server = Flask(__name__, static_folder="./MathJax")
    CORS(server)  # 允许跨域请求
    werkzeug_log = logging.getLogger("werkzeug")
    werkzeug_log.disabled = True  # 禁用请求日志
    werkzeug_log.propagate = False  # 阻止日志传播到父级
    server.run(host="0.0.0.0", port=5000, threaded=True)
