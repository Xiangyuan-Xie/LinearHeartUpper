from typing import Tuple, Optional

import numpy as np
from pymodbus.client import ModbusTcpClient
from pymodbus.pdu import ModbusPDU
from pymodbus.pdu.mei_message import ReadDeviceInformationRequest


def interval_encode(a_array: np.ndarray, b_array: np.ndarray) -> np.ndarray:
    """
    三次样条插值区间编码
    :param a_array: 区间起点数组，shape=(N,)
    :param b_array: 区间终点数组，shape=(N,)
    :return: 编码后的16位整型数组，shape=(N,)
    """
    # 输入校验
    assert a_array.shape == b_array.shape, "数组维度必须一致"
    assert np.all((a_array >= 0) & (a_array <= 1)), "起点值超出[0,1]范围"
    assert np.all((b_array >= 0) & (b_array <= 1)), "终点值超出[0,1]范围"
    assert np.all(a_array <= b_array), "存在起点大于终点的非法区间"

    # 浮点量化
    a_quantized = np.round(a_array * 255).astype(np.uint16)
    b_quantized = np.round(b_array * 255).astype(np.uint16)

    # 位运算编码
    return (a_quantized << 8) | b_quantized


def interval_decode(encoded_array: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    三次样条插值区间解码
    :param encoded_array: 16位整型编码数组，shape=(N,)
    :return: 元组包含两个浮点数组（起点数组，终点数组），shape=(N,)
    """
    # 输入校验
    assert np.issubdtype(encoded_array.dtype, np.integer), "编码数组必须是整型"
    assert np.all((encoded_array >= 0) & (encoded_array <= 0xFFFF)), "编码值超出16位范围"

    # 位运算解码
    a_quantized = (encoded_array >> 8).astype(np.uint16)  # 提取高8位
    b_quantized = (encoded_array & 0xFF).astype(np.uint16)  # 提取低8位

    # 浮点反量化
    a_array = a_quantized.astype(np.float64) / 255.0
    b_array = b_quantized.astype(np.float64) / 255.0

    # 后置条件验证
    assert np.all(a_array <= b_array), "解码后存在起点大于终点的异常数据"
    return a_array, b_array


class SplineCoefficientCompressor:
    def __init__(self, max_abs_value: float=1e6, mu: int=255):
        """
        :param max_abs_value: 系数的最大绝对值范围
        :param mu: μ-law压缩的参数，控制非线性量化程度
        """
        self.max_abs_value = max_abs_value
        self.mu = mu
        self.scale_factor = (2 ** 19 - 1) / np.log1p(mu)

    def _mu_law_compress(self, x: np.ndarray) -> np.ndarray:
        """
        μ-law非线性压缩算法（前向变换）
        :param x: 输入系数矩阵
        :return 压缩后的归一化值，范围[-1, 1]
        """
        x_norm = x / self.max_abs_value
        return np.sign(x_norm) * np.log1p(self.mu * np.abs(x_norm)) / np.log1p(self.mu)

    def _mu_law_expand(self, y: np.ndarray) -> np.ndarray:
        """
        μ-law非线性解压缩算法（逆向变换）
        :param y: 压缩后的归一化值
        :return: 恢复后的原始量级系数
        """
        return np.sign(y) * (np.power(1 + self.mu, np.abs(y)) - 1) / self.mu * self.max_abs_value

    def compress(self, coefficients: np.ndarray) -> np.ndarray:
        """
        压缩(19位量化+高低位拆分)
        :param coefficients: 原始样条系数矩阵，shape=(N,4)
        :return 压缩后的寄存器数据，shape=(N,5)，前4列为4个系数的低16位，第5列为4个系数的高3位打包存储（每个系数3bit，共12bit）
        """
        # μ-law压缩
        compressed = self._mu_law_compress(coefficients)
        quantized = np.clip(compressed * (2 ** 19 - 1), -2 ** 19, 2 ** 19 - 1).astype(np.int32)

        # 拆分高低位
        low_bits = quantized & 0xFFFF  # 取低16位
        high_bits = ((quantized >> 16) & 0xF).astype(np.uint16)  # 取高3位（保留4bit空间）
        reg_high = np.zeros((coefficients.shape[0], 1), dtype=np.uint32)
        for i in range(4):
            reg_high[:, 0] |= (high_bits[:, i].astype(np.uint32) & 0xF) << (4 * i)
        return np.hstack([low_bits.astype(np.uint16), reg_high.astype(np.uint16)])

    def decompress(self, registers: np.ndarray) -> np.ndarray:
        """
        解压缩(数据重组+非线性展开)
        :param registers: 压缩后的寄存器数据，shape=(N,5)
        :return 恢复的原始样条系数矩阵，shape=(N,4)
        """
        # 合并高低位
        low_bits = registers[:, :4].astype(np.int32)
        reg_high = registers[:, 4]
        high_bits = np.zeros((registers.shape[0], 4), dtype=np.int32)
        for i in range(4):
            high_bits[:, i] = (reg_high >> (4 * i)) & 0xF
        quantized = (high_bits << 16) | low_bits
        quantized = np.where(quantized >= 2 ** 19, quantized - 2 ** 20, quantized)  # 处理符号扩展

        # μ-law解压
        y = quantized / (2 ** 19 - 1)
        return self._mu_law_expand(y)


def float_to_fixed(arr: np.ndarray, frac_bits: int = 16, byte_order: str = '>') -> np.ndarray:
    """
    批量将浮点数转换为Q格式定点数并拆分为高/低16位
    :param arr: 目标浮点数组，shape=(1,N)
    :param frac_bits: 小数部分位数
    :param byte_order: 端序
    :return: 拆分为高/低16位的定点数组，shape=(1,2N)
    """
    assert byte_order in ('>', '<'), "无效的端序！"

    # 计算缩放因子和取值范围
    scale = 1 << frac_bits
    max_val = (1 << (31 - frac_bits)) - (1.0 / scale)
    min_val = - (1 << (31 - frac_bits))

    # 饱和处理
    arr = np.clip(arr, min_val, max_val)

    # 转换为Q格式定点数
    scaled = (arr * scale).astype(np.int32)

    # 分离高低位
    high_bits = (scaled >> 16).astype(np.uint16)  # 取高16位
    low_bits = (scaled & 0xFFFF).astype(np.uint16)  # 取低16位

    # 创建交替数组
    result = np.empty(2 * len(arr), dtype=np.uint16)
    if byte_order == '<':
        result[0::2] = low_bits
        result[1::2] = high_bits
    else:
        result[0::2] = high_bits
        result[1::2] = low_bits

    return result


def fixed_to_float(arr: np.ndarray, frac_bits: int = 16, byte_order: str = '>') -> np.ndarray:
    """
    将高/低16位交替的定点数组还原为浮点数组
    :param arr: 包含高低位的定点数组，shape=(1,2N)
    :param frac_bits: 小数部分位数
    :param byte_order: 端序
    :return: 还原后的浮点数组，shape=(1,N)
    """
    # 验证参数合法性
    assert byte_order in ('>', '<'), "无效的端序！"
    assert arr.size % 2 == 0, "输入数组长度必须为偶数"

    # 展平处理以简化索引操作
    flattened = arr.ravel()

    # 分离高低位数据
    if byte_order == '>':
        high_bits = flattened[0::2].astype(np.uint32)  # 大端序：高位在前
        low_bits = flattened[1::2].astype(np.uint32)
    else:
        high_bits = flattened[1::2].astype(np.uint32)  # 小端序：高位在后
        low_bits = flattened[0::2].astype(np.uint32)

        # 合并32位整数
    combined = (high_bits << 16) | low_bits

    # 转换回有符号整数
    fixed_point = combined.astype(np.int32)

    # 计算缩放因子
    scale = 1 << frac_bits

    return fixed_point.astype(np.float64) / scale


def split_array(arr: np.ndarray, max_length: int=120):
    """
    分割数组
    :param arr:  编码后的一维数据包
    :param max_length: 每个列表的最大长度（默认120）
    :return 二维列表
    """
    # 计算需要分割的块数
    n = len(arr)
    num_chunks = (n + max_length - 1) // max_length  # 向上取整

    # 按顺序分割为子列表
    chunks = [
        arr[i * max_length: (i + 1) * max_length].tolist()
        for i in range(num_chunks)
    ]

    return chunks


def process_write_response(response: ModbusPDU) -> int:
    """
    处理写入请求的响应
    :param response: ModbusPDU包
    :return: 处理结果
    """
    if response is None or response.isError():
        return False

    return True


def process_read_response(response: ModbusPDU) -> tuple[bool, Optional[ModbusPDU]]:
    """
    处理读取请求的响应
    :param response: ModbusPDU包
    :return: 处理结果
    """
    if response is None or response.isError():
        return False, response

    return True, response


def check_client_status(client: Optional[ModbusTcpClient]) -> bool:
    """
    检查PLC连接状态
    :param client: ModbusTcp客户端对象
    :return: 连接状态
    """
    if client is not None and client.connect() and client.is_socket_open():
        try:
            client.execute(False, ReadDeviceInformationRequest())
            return True
        except ConnectionResetError:
            return False

    return False
