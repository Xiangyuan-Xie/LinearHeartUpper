import numpy as np

from linearheart.utils.communication import fixed_to_float, float_to_fixed


def compute_quantization_error(original: np.ndarray, decoded: np.ndarray):
    # 差值
    diff = decoded - original

    # 绝对误差
    abs_error = np.abs(diff)
    max_abs_error = np.max(abs_error)
    mean_abs_error = np.mean(abs_error)
    mse = np.mean(diff**2)

    # 相对误差处理（避免除以0）
    with np.errstate(divide="ignore", invalid="ignore"):
        relative_error = np.where(np.abs(original) > 1e-8, abs_error / np.abs(original), 0.0)
    max_rel_error = np.max(relative_error)
    mean_rel_error = np.mean(relative_error)

    return max_abs_error, mean_abs_error, mse, max_rel_error, mean_rel_error


original = np.random.uniform(low=-32768, high=32768, size=10000).astype(np.float32)
encoded = float_to_fixed(original)
decoded = fixed_to_float(encoded)

# 误差计算
max_abs_error, mean_abs_error, mse, max_rel_error, mean_rel_error = compute_quantization_error(original, decoded)

# 打印结果
print(f"最大绝对误差（Max Error）: {max_abs_error:.8f}")
print(f"平均绝对误差（Mean Absolute Error）: {mean_abs_error:.8f}")
print(f"均方误差（Mean Squared Error）: {mse:.8f}")
print(f"最大相对误差（Max Relative Error）: {max_rel_error * 100:.4f}%")
print(f"平均相对误差（Mean Relative Error）: {mean_rel_error * 100:.4f}%")
