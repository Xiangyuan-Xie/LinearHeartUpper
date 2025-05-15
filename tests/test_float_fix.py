import numpy as np

from communication import fixed_to_float, float_to_fixed


def test_fixed_point_conversion():
    """
    测试浮点与定点数转换的精度损失
    """
    # 原始输入数据
    original = np.array([-27.7879706, 8.08080747, 0.452924949, 0.404347826], dtype=np.float32)

    # 执行编码解码流程
    encoded = float_to_fixed(original)
    decoded = fixed_to_float(encoded)

    # 计算最大绝对误差
    max_error = np.max(np.abs(original - decoded))

    # 断言误差在可接受范围内（根据实际业务需求调整阈值）
    assert max_error <= 1e-4, f"最大误差 {max_error} 超过阈值 1e-4，实际误差：{original - decoded}"

    # 可选：输出调试信息（pytest默认不显示，需加-s参数）
    print("\n验证结果：" f"\n原始值：{original}" f"\n解码值：{decoded}" f"\n误差值：{original - decoded}")
