from typing import Optional

import numpy as np
from loguru import logger
from pymodbus.pdu import ModbusPDU

from widget.status_light import StatusLight


def float_to_fixed(arr: np.ndarray, frac_bits: int = 16, byte_order: str = '<') -> np.ndarray:
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


def fixed_to_float(arr: np.ndarray, frac_bits: int = 16, byte_order: str = '<') -> np.ndarray:
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
    :param arr: 编码后的一维数据包
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


def process_write_response(response: ModbusPDU, response_type: str="未知寄存器") -> bool:
    """
    处理写入请求的响应
    :param response: ModbusPDU包
    :param response_type: 寄存器类型
    :return: 处理结果
    """
    if response is None:
        logger.error(f"请求写入{response_type}时未响应！")
        return False
    elif response.isError():
        logger.error(f"写入{response_type}[{response.address}]失败，"
                     f"内容：{response.bits if response_type == "线圈" else response.registers}")
        return False
    else:
        logger.info(f"写入{response_type}[{response.address}]成功，"
                    f"内容：{response.bits if response_type == "线圈" else response.registers}")
        return True


def process_read_response(response: ModbusPDU, response_type: str="未知寄存器") -> tuple[bool, Optional[ModbusPDU]]:
    """
    处理读取请求的响应
    :param response: ModbusPDU包
    :param response_type: 寄存器类型
    :return: 处理结果
    """
    if response is None:
        logger.error(f"请求读取{response_type}时未响应！")
        return False, None
    elif response.isError():
        logger.error(f"读取{response_type}[{response.address}]失败！")
        return False, response
    else:
        logger.info(f"读取{response_type}[{response.address}]成功，"
                    f"内容：{response.bits if response_type == "线圈" else response.registers}")
        return True, response


def process_status_code(status_code: int) -> tuple[StatusLight.Color, str]:
    """
    处理电机状态码
    :param status_code: 状态码
    :return 当前状态
    """
    if status_code == 1:
        return StatusLight.Color.Grey, "离线"
    elif status_code in [2, 3]:
        return StatusLight.Color.Orange, "回零"
    elif status_code == 4:
        return StatusLight.Color.Green, "就绪"
    elif status_code == 5:
        return StatusLight.Color.Orange, "工作"
    elif status_code in [6, 7]:
        return StatusLight.Color.Red, "故障"
    else:
        return StatusLight.Color.Grey, "未知"
