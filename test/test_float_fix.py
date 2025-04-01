import numpy as np

from communication import float_to_fixed, fixed_to_float

original = np.array([-27.7879706, 8.08080747, 0.452924949, 0.404347826], dtype=np.float32)
encoded = float_to_fixed(original)
decoded = fixed_to_float(encoded)

print("原始值：", original)
print("解码值：", decoded)
print("最大误差：", np.max(np.abs(original - decoded)))