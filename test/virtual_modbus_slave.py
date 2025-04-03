import bisect
import logging
import time
from threading import Thread, Event, Lock

import numpy as np
from pymodbus.datastore import ModbusSequentialDataBlock
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.server import StartTcpServer

from communication import fixed_to_float, float_to_fixed


class ModbusVirtualSlave:
    def __init__(self, slave_id=1, port=502, address='0.0.0.0'):
        """
        初始化虚拟从站
        :param slave_id: 从站设备ID (默认1)
        :param port: 监听端口 (默认502)
        :param address: 绑定地址 (默认0.0.0.0)
        """
        self.slave_id = slave_id
        self.port = port
        self.address = address

        self._stop_thread_flag = Event()
        self._update_thread = None
        self._lock = Lock()

        # 数据存储
        self.data_store = {
            'hr': ModbusSequentialDataBlock(0x6000, [0] * 16384),  # 保持寄存器
            'ir': ModbusSequentialDataBlock(0x2000, [0] * 16384),  # 输入寄存器
            'co': None,  # 线圈
            'di': None  # 离散输入
        }
        self.slave_context = ModbusSlaveContext(
            hr=self.data_store['hr'],
            ir=self.data_store['ir'],
            co=self.data_store['co'],
            di=self.data_store['di']
        )
        self.context = ModbusServerContext(slaves={slave_id: self.slave_context}, single=False)

    def start_server(self):
        """
        启动ModbusTCP虚拟从站
        """
        try:
            self._update_thread = Thread(target=self._update_task, daemon=True)
            self._update_thread.start()

            StartTcpServer(
                context=self.context,
                address=(self.address, self.port)
            )
        except Exception as e:
            logging.error(f"Modbus虚拟从站启动失败: {e}！")

    def _update_task(self):
        """
        数据更新线程任务
        """
        coefficients = []
        start_time = None
        while not self._stop_thread_flag.is_set():
            flag = self.get_holding_registers(0x6000, 1)[0]
            if flag == 2:  # 参数更新
                coefficients.clear()
                number_coefficient = self.get_holding_registers(0x6001, 1)[0]
                for i in range(number_coefficient):
                    decoded_coefficient = fixed_to_float(
                        np.array(self.get_holding_registers(0x6010 + 10 * i, 12)))
                    coefficients.append(decoded_coefficient.tolist())
                self.set_holding_registers(0x6000, [1])
                start_time = time.time()
            elif flag == 1:  # 正常运行
                position = interpolation((time.time() - start_time) % 1, coefficients)
                encoded_position = float_to_fixed(np.array([position]))
                self.set_holding_registers(0x6002, encoded_position.tolist())
            else:
                continue

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

    return a * dx ** 3 + b * dx ** 2 + c * dx + d


if __name__ == "__main__":
    # 启用调试日志
    logging.basicConfig()
    logging.getLogger().setLevel(logging.INFO)

    # 创建并启动虚拟从站
    slave = ModbusVirtualSlave()
    logging.info("Modbus虚拟从站已启动！")
    slave.start_server()
