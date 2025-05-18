# LinearHeart：基于直线电机的体外心脏模拟系统

---

![Python Version](https://img.shields.io/badge/python-3.12-blue)

> 北京科技大学机械工程学院2025届本科毕业设计。

## 🚀 功能简介
<img src="docs\UI.png" alt=""/>

- 自由设置波形关键点，自动根据关键点完成拟合波形曲线。
- 支持波形关键点和设置参数的保存与重新读取。
- 实时显示模拟波形，并支持导出模拟波形点集。
- 实时显示反馈波形，并支持录制保存反馈点集。
- 轻松完成电机的一站式操作。

## ⚙️ 安装依赖库
本项目基于`Python 3.12`开发，你可以通过以下命令安装所需的依赖库：
```bash
  pip install -e .
```

## 📦 工程化部署
Python项目在工程化部署中存在诸多不便，你可以使用以下方法生成本项目的可执行文件：
### 方法1：Pyinstaller
- 安装`Pyinstaller`
```bash
  pip install pyinstaller
```
- 生成可执行程序
```bash
  pyinstaller --onefile --noconsole --add-data "MathJax:MathJax" main.py
```
### 方法2：Nuitka
- 安装`Nuitka`
```bash
  pip install nuitka
```
- 生成可执行程序
```bash
  nuitka --onefile --windows-console-mode=disable --include-package=scipy --enable-plugin=pyside6 --mingw64 --include-data-dir=MathJax=MathJax main.py
```

## 🙌 致谢
- 感谢 [齐昕](https://me.ustb.edu.cn/shiziduiwu/jiaoshixinxi/2022-03-24/530.html) 老师为本项目提供的指导和支持！

## 🌟 作者
- 姓名：[谢翔远](https://github.com/Xiangyuan-Xie)  
- 学校：[北京科技大学](https://www.ustb.edu.cn/)  
- Email：[DragonBoat_XXY@163.com](mailto:DragonBoat_XXY@163.com)