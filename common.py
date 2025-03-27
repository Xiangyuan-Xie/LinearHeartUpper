import struct

import numpy as np


def get_method_index(method_name: str) -> int:
    """
    获取插值方法的索引
    :param method_name: 插值方法名称
    :return: 插值方法索引
    """
    if method_name == "Lagrange":
        return 0
    elif method_name == "Cubic Spline":
        return 1
    else:
        raise ValueError("试图通过不支持的插值方法获取索引！")


def unsigned_combine(a: int, b: int) -> int:
    """
    将两个无符号整数拼接为16位二进制数
    :param a: 4位无符号整数
    :param b: 12位无符号整数
    :return: 16位二进制数
    """
    assert 0 <= a <= 15 and 0 <= b <= 4095, "尝试拼接不符合范围的两个整数！"
    return (a << 12) | b


def int32_struct(num: int, byte_order: str = '>') -> tuple:
    """
    将int32拆分为高16位和低16位
    :param num: 目标数字
    :param byte_order: 端序
    :return: 高16位字节和低16位字节
    """
    packed_bytes = struct.pack(f'{byte_order}i', num)
    high_16 = struct.unpack(f'{byte_order}H', packed_bytes[:2])[0]
    low_16 = struct.unpack(f'{byte_order}H', packed_bytes[2:4])[0]
    return high_16, low_16


def generate_packet(method: str, coefficient_matrix: np.ndarray, byte_order: str = '>') -> list:
    """
    生成通信数据包
    :param method: 插值方法
    :param coefficient_matrix: 系数矩阵
    :param byte_order: 端序
    :return:
    """
    assert byte_order in ('>', '<'), "尝试在生成Packet时传入无法识别的端序！"

    # 拼接系数矩阵
    coefficient_matrix *= 1000
    coefficient_matrix = np.rint(coefficient_matrix).astype(int)
    if coefficient_matrix.ndim > 1:
        coefficient_matrix = np.concatenate(coefficient_matrix)

    # 插值方法和帧长度
    packet = [unsigned_combine(get_method_index(method), len(coefficient_matrix))]

    # 系数
    for coefficient in coefficient_matrix:
        high_16, low_16 = int32_struct(coefficient, byte_order)
        if byte_order == '>':
            packet.append(high_16)
            packet.append(low_16)
        else:
            packet.append(low_16)
            packet.append(high_16)

    return packet
