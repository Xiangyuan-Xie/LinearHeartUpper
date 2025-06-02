import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import rcParams

# 设置中文字体与负号显示
rcParams["font.family"] = "Microsoft YaHei"
rcParams["axes.unicode_minus"] = False

# 读取数据
df_feedback = pd.read_csv("G:/GraduationDesign/linearheart/core/output.csv")
df_mock = pd.read_csv("G:/GraduationDesign/linearheart/core/test.csv")

# 截取反馈波形指定区间
start_index = 32500
end_index = 32990
subset = df_feedback["Position"].iloc[start_index:end_index]
feedback_x = np.linspace(0, 1, len(subset.values))
feedback_y = subset.values

# 获取模拟波形
mock_x = df_mock["x"]
mock_y = df_mock["y"]

# === 插值对齐模拟波形 ===
mock_y_interp = np.interp(feedback_x, mock_x, mock_y)

# === 误差计算 ===
abs_error = np.abs(feedback_y - mock_y_interp)
mse = np.mean((feedback_y - mock_y_interp) ** 2)

# === 相对误差：对参考值小于阈值的点不计入计算 ===
threshold = 1.0  # 设置最小参考值，单位 mm
valid_mask = np.abs(mock_y_interp) > threshold

rel_error = np.zeros_like(abs_error)
rel_error[valid_mask] = abs_error[valid_mask] / np.abs(mock_y_interp[valid_mask])

# === 统计误差指标 ===
max_abs_error = np.max(abs_error)
mean_abs_error = np.mean(abs_error)
max_rel_error = np.max(rel_error) if np.any(valid_mask) else np.nan
mean_rel_error = np.mean(rel_error[valid_mask]) if np.any(valid_mask) else np.nan

# === 输出误差结果 ===
print("误差指标：")
print(f"最大绝对误差: {max_abs_error:.4f} mm")
print(f"平均绝对误差: {mean_abs_error:.4f} mm")
print(f"均方误差(MSE): {mse:.4f} mm²")
print(f"最大相对误差: {max_rel_error*100:.4f} %" if not np.isnan(max_rel_error) else "最大相对误差: 无有效值")
print(f"平均相对误差: {mean_rel_error*100:.4f} %" if not np.isnan(mean_rel_error) else "平均相对误差: 无有效值")

# === 绘图：并列子图 ===
fig, axs = plt.subplots(1, 2, figsize=(12, 4), sharey=True)

# 子图1：反馈波形
axs[0].plot(feedback_x, feedback_y, label="反馈波形", linewidth=1.5)
axs[0].set_title("反馈波形")
axs[0].set_xlabel("归一化时间")
axs[0].set_ylabel("电机位置 (mm)")
axs[0].set_ylim(-7.5, 57.5)
axs[0].grid(True)
axs[0].legend()

# 子图2：模拟波形
axs[1].plot(mock_x, mock_y, label="模拟波形", linewidth=1.5, color="orange")
axs[1].set_title("模拟波形")
axs[1].set_xlabel("归一化时间")
axs[1].set_ylim(-7.5, 57.5)
axs[1].grid(True)
axs[1].legend()

plt.tight_layout()
plt.show()
