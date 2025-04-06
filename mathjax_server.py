from flask import Flask
from flask_cors import CORS


def run_server():
    server = Flask(__name__, static_folder="./MathJax")
    CORS(server)  # 允许跨域请求
    server.run(host='0.0.0.0', port=5000, threaded=True)
