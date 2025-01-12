from pymodbus.client import ModbusTcpClient


class ModbusTCPClient:
    def __init__(self, host):
        self.client = ModbusTcpClient(host)

    def send_read_request(self, address):
        """
        发送读取保持寄存器的请求

        :param address: 起始地址
        :return: 响应结果
        """
        try:
            response = self.client.read_holding_registers(address)
            if response.isError():
                print(f"读取失败: {response}")
            else:
                print(f"读取成功: {response.registers}")
            return response
        except Exception as e:
            print(f"发生错误: {e}")

    def send_write_request(self, address, value):
        """
        发送写单个保持寄存器的请求

        :param address: 寄存器地址
        :param value: 写入的值
        :return: 响应结果
        """
        try:
            response = self.client.write_register(address, value)
            if response.isError():
                print(f"写入失败: {response}")
            else:
                print(f"写入成功: 地址 {address}, 值 {value}")
            return response
        except Exception as e:
            print(f"发生错误: {e}")
