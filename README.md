# 本科毕业设计：基于直线电机的人工心脏驱动系统LinearHeart

---

![Python Version](https://img.shields.io/badge/python-%3E%3D%203.11-blue)

> 直线电机心脏驱动系统PC端。

## 👉 功能简介
<img src="Doc\UI.png" alt=""/>

- 完全自定义的波形设置，根据用户设置自动计算运行参数。
- 支持波形设置的保存与读取，快速还原历史波形，避免重复设置。
- 实时显示反馈数据，系统运行情况一目了然。
- 实时显示模拟波形，轻松预知系统运行情况。

## 🚀 安装依赖库
本项目推荐使用 Python 3.11 及以上版本进行开发，并使用 pip 工具来安装所需的依赖库。你可以通过以下命令安装所需的依赖库：
```bash
  pip install -r requirements.txt
```

## 📦 生成可执行文件
将本项目使用可执行文件部署是个不错的选择，你可以使用以下2种方法将Python代码编译为可执行文件：
### 1. Pyinstaller
- 安装`Pyinstaller`
```bash
  pip install pyinstaller
```
- 生成可执行程序
```bash
  pyinstaller --onefile --noconsole --add-data "MathJax:MathJax" main.py
```
### 2. Nuitka
- 安装`Nuitka`
```bash
  pip install nuitka
```
- 生成可执行程序
```bash
  nuitka --onefile --windows-console-mode=disable --enable-plugin=pyside6 --mingw64 --include-data-dir=MathJax=MathJax main.py
```

## 🙌 致谢
- 感谢 [齐昕](https://me.ustb.edu.cn/shiziduiwu/jiaoshixinxi/2022-03-24/530.html) 老师在研发过程中提供的指导和支持！
- 感谢 [MathJax](https://www.mathjax.org/) 助力数学公式的优雅呈现！

## 🌟 作者
- 🧑‍💻 姓名：[谢翔远](https://github.com/Xiangyuan-Xie)  
- 🏫 学校：[北京科技大学](https://www.ustb.edu.cn/)  
- ✉️ Email：[DragonBoat_XXY@163.com](mailto:DragonBoat_XXY@163.com)