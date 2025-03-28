import numpy as np

from communication import SplineCoefficientCompressor


if __name__ == "__main__":
    # 初始化参数
    max_abs = 1e6
    compressor = SplineCoefficientCompressor(max_abs_value=max_abs)

    # 生成测试数据（包含极端值和随机值）
    test_cases = [
        np.full((100, 4), max_abs),  # 最大值边界
        np.full((100, 4), -max_abs),  # 最小值边界
        np.random.normal(0, max_abs / 3, (1000, 4)),  # 正态分布随机值
        np.linspace(-max_abs, max_abs, 400).reshape(100, 4),  # 线性分布
        np.zeros((50, 4))  # 零值测试
    ]

    all_abs_errors = []
    all_rel_errors = []

    for idx, coefficients in enumerate(test_cases):
        # 执行压缩-解压流程
        compressed = compressor.compress(coefficients)
        restored = compressor.decompress(compressed)

        # 误差计算
        abs_errors = np.abs(coefficients - restored)
        rel_errors = np.divide(abs_errors, np.abs(coefficients),
                               where=(coefficients != 0),  # 避免除以零
                               out=np.zeros_like(abs_errors))

        # 过滤无效相对误差（零输入时）
        valid_rel_errors = rel_errors[coefficients != 0]

        # 记录统计量
        stats = {
            "case": idx + 1,
            "max_abs": np.max(abs_errors),
            "mean_abs": np.mean(abs_errors),
            "median_abs": np.median(abs_errors),
            "max_rel": np.max(valid_rel_errors) if valid_rel_errors.size > 0 else 0,
            "mean_rel": np.mean(valid_rel_errors) if valid_rel_errors.size > 0 else 0
        }

        all_abs_errors.append(abs_errors)
        all_rel_errors.append(valid_rel_errors)

        # 打印详细统计
        print(f"\nCase {idx + 1} Results:")
        print(f"最大绝对误差: {stats['max_abs']:.4e}")
        print(f"平均绝对误差: {stats['mean_abs']:.4e}")
        print(f"中位数绝对误差: {stats['median_abs']:.4e}")
        print(f"最大相对误差: {stats['max_rel']:.4%}")
        print(f"平均相对误差: {stats['mean_rel']:.4%}")

    # 综合误差分析
    combined_abs = np.concatenate(all_abs_errors)
    combined_rel = np.concatenate([x for x in all_rel_errors if x.size > 0])

    print("\n全局统计:")
    print(f"总样本数: {combined_abs.size}")
    print(f"全局最大绝对误差: {np.max(combined_abs):.4e}")
    print(f"全局平均绝对误差: {np.mean(combined_abs):.4e}")
    print(f"全局最大相对误差: {np.max(combined_rel):.4%}")
    print(f"全局平均相对误差: {np.mean(combined_rel):.4%}")

    # 修改后的示例展示代码
    sample_case_idx = 2  # 指定使用第三个测试用例的恢复数据
    sample_idx = np.random.randint(0, test_cases[sample_case_idx].shape[0])
    restored_data = compressor.decompress(compressor.compress(test_cases[sample_case_idx]))

    print("\n随机样本对比（Case 3）:")
    print(f"原始值: {test_cases[sample_case_idx][sample_idx]}")
    print(f"恢复值: {restored_data[sample_idx]}")
    print(f"绝对误差: {np.abs(test_cases[sample_case_idx][sample_idx] - restored_data[sample_idx])}")