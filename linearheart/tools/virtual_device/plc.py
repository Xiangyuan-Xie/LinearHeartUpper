import bisect
import time
from threading import Event, Thread

import numpy as np
from loguru import logger
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartTcpServer

from linearheart.common.common import RegisterAddress
from linearheart.utils.communication import fixed_to_float, float_to_fixed


class ModbusVirtualSlave:
    def __init__(self, slave_id=1, port=502, address="0.0.0.0"):
        """
        :param slave_id: 从站设备ID (默认1)
        :param port: 监听端口 (默认502)
        :param address: 绑定地址 (默认0.0.0.0)
        """
        self.slave_id = slave_id
        self.port = port
        self.address = address

        self._stop_thread_flag = Event()
        self._update_thread = None

        # 数据存储
        self.data_store = {
            "hr": ModbusSequentialDataBlock(0x6000, [0] * 16384),  # 保持寄存器
            "ir": ModbusSequentialDataBlock(0x2000, [0] * 16384),  # 输入寄存器
            "co": None,  # 线圈
            "di": None,  # 离散输入
        }
        self.slave_context = ModbusSlaveContext(
            hr=self.data_store["hr"], ir=self.data_store["ir"], co=self.data_store["co"], di=self.data_store["di"]
        )
        self.context = ModbusServerContext(slaves={slave_id: self.slave_context}, single=False)

    def start_server(self):
        """
        启动ModbusTCP虚拟从站
        """
        try:
            logger.info("Modbus virtual slave start！")

            self._update_thread = Thread(target=self._update_task, daemon=True)
            self._update_thread.start()

            StartTcpServer(context=self.context, address=(self.address, self.port))
        except Exception as e:
            logger.error(f"Modbus virtual slave fail: {e}！")

    def _update_task(self):
        """
        数据更新线程任务
        """
        coefficients = []
        frequency = None
        start_time = None
        while not self._stop_thread_flag.is_set():
            status = self.get_holding_registers(RegisterAddress.Status, 1)[0]
            power = self.get_holding_registers(RegisterAddress.Power, 1)[0]

            # 通电
            if power == 1:
                # 参数更新
                if status == 2:
                    coefficients.clear()

                    frequency = fixed_to_float(
                        np.array(self.get_holding_registers(RegisterAddress.Frequency, 2))
                    ).item()
                    number_of_interval = self.get_holding_registers(RegisterAddress.NumberOfInterval, 1)[0]
                    for i in range(number_of_interval):
                        decoded_coefficient = fixed_to_float(
                            np.array(self.get_holding_registers(RegisterAddress.Coefficients + 10 * i, 12))
                        )
                        coefficients.append(decoded_coefficient.tolist())

                    self.set_holding_registers(RegisterAddress.Status, [1])
                    start_time = time.time()
                    logger.info(f"Receive new run parameters: {frequency} Hz, {number_of_interval} intervals!")

                # 正常运行
                elif status == 1:
                    position = interpolation(((time.time() - start_time) % 1) / frequency, coefficients)
                    encoded_position = float_to_fixed(np.array([position]))
                    self.set_holding_registers(RegisterAddress.Position, encoded_position.tolist())

            # 断电
            else:
                if status != 0:
                    self.set_holding_registers(RegisterAddress.Status, [0])

    def stop_server(self):
        """
        停止ModbusTCP虚拟从站
        """
        self._stop_thread_flag.set()
        self._update_thread.join()

    def get_holding_registers(self, address, count=1):
        """
        读取保持寄存器数据
        """
        return self.slave_context.getValues(3, address, count)

    def set_holding_registers(self, address, values):
        """
        写入保持寄存器数据
        """
        self.slave_context.setValues(3, address, values)

    def get_input_registers(self, address, count=1):
        """
        读取输入寄存器数据
        """
        return self.slave_context.getValues(4, address, count)

    def set_input_registers(self, address, values):
        """
        写入输入寄存器数据
        """
        self.slave_context.setValues(4, address, values)


def interpolation(x, coefficients):
    """
    插值计算函数
    :param x : 需要插值的x坐标
    :param coefficients : 参数列表，每个元素结构为[x0, a, b, c, d, x1]
    :return: 插值结果y值
    """
    # 提取区间左端点列表
    x0_list = [spline[0] for spline in coefficients]

    # 二分查找定位区间
    i = bisect.bisect_right(x0_list, x) - 1

    # 边界检查
    if i < 0 or i >= len(coefficients):
        min_x = coefficients[0][0]
        max_x = coefficients[-1][-1]
        raise ValueError(f"x={x} 超出区间范围[{min_x}, {max_x}]")

    # 解析参数
    x0, a, b, c, d, x1 = coefficients[i]
    dx = x - x0

    return a * dx**3 + b * dx**2 + c * dx + d


if __name__ == "__main__":
    slave = ModbusVirtualSlave()
    slave.start_server()
