# 毕业设计：直线电机心脏驱动系统LinearHeart

---

![Python Version](https://img.shields.io/badge/python-%3E%3D%203.11-blue)

> 直线电机心脏驱动系统PC端。

## 👉 功能简介
<img src="Doc\UI.png"/>

- 完全自定义的波形设置，自动通过用户设置的插值点计算插值表达式和绘制插值曲线，支持拉格朗日插值和三次样条插值两种方法。
- 支持波形设置保存与读取，避免重复操作，提高工作效率。
- 支持与PLC进行通信，借助通信链路，可让电机一键执行用户设置好的波形，操作简单快捷，

## 🚀 安装依赖库
本项目推荐使用 Python 3.11 及以上版本进行开发，并使用 pip 工具来安装所需的依赖库。你可以通过以下命令安装所需的依赖库：
```bash
  pip install -r requirements.txt
```

## 📦 生成可执行文件
如果存在在其他环境的部署需求，使用可执行文件进行部署是个不错的选择。此处会介绍两种使用Python代码生成可执行文件的方式。
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
  nuitka --onefile --windows-console-mode=disable --include-data-dir=MathJax=MathJax main.py
```

## 🙌 致谢
- 感谢我的指导老师 [齐昕](https://me.ustb.edu.cn/shiziduiwu/jiaoshixinxi/2022-03-24/530.html)，在本项目的研发过程中提供宝贵的指导和支持。

## 🌟 作者
- 🧑‍💻 姓名：谢翔远  
- 🏫 学校：北京科技大学  
- ✉️ Email：[DragonBoat_XXY@163.com](mailto:DragonBoat_XXY@163.com)
- 🐱 GitHub：[Xiangyuan-Xie](https://github.com/Xiangyuan-Xie)