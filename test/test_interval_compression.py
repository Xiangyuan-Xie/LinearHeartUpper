import numpy as np

from communication import interval_encode, interval_decode


def batch_measure_error(original_a: np.ndarray, original_b: np.ndarray,
                        decoded_a: np.ndarray, decoded_b: np.ndarray) -> dict:
    # 绝对误差计算
    a_abs_err = np.abs(original_a - decoded_a)
    b_abs_err = np.abs(original_b - decoded_b)

    # 相对误差计算（避免除以零）
    a_rel_err = np.divide(a_abs_err, original_a,
                          out=np.zeros_like(a_abs_err),
                          where=(original_a != 0))
    b_rel_err = np.divide(b_abs_err, original_b,
                          out=np.zeros_like(b_abs_err),
                          where=(original_b != 0))

    return {
        'a_abs': a_abs_err,
        'b_abs': b_abs_err,
        'a_rel': a_rel_err,
        'b_rel': b_rel_err
    }


if __name__ == '__main__':
    # 批量生成测试数据
    N = 1000000
    a = np.random.uniform(0, 1, N)
    b = a + np.random.uniform(0, 1 - a)  # 保证a <= b

    # 向量化编码解码
    encoded = interval_encode(a, b)
    decoded_a, decoded_b = interval_decode(encoded)

    # 批量计算误差
    errors = batch_measure_error(a, b, decoded_a, decoded_b)

    # 统计指标计算
    stats = {
        'max_a_abs': np.max(errors['a_abs']),
        'max_b_abs': np.max(errors['b_abs']),
        'mean_a_rel': np.mean(errors['a_rel'][errors['a_rel'] > 0]),
        'mean_b_rel': np.mean(errors['b_rel'][errors['b_rel'] > 0])
    }

    # 格式化输出
    print(f"最大绝对误差统计（样本量{N}）:")
    print(f"  a起点: {stats['max_a_abs']:.6f} (理论上限: {1 / (2 * 255):.6f})")
    print(f"  b终点: {stats['max_b_abs']:.6f} (理论上限: {1 / (2 * 255):.6f})")
    print("\n有效平均相对误差（排除零值）:")
    print(f"  a起点: {stats['mean_a_rel']:.6%}")
    print(f"  b终点: {stats['mean_b_rel']:.6%}")
