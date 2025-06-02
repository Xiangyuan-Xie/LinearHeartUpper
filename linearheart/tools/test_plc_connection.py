from pymodbus.client import ModbusTcpClient

from linearheart.common.common import RegisterAddress


def fixed_bin(num, bits=16):
    return f"0b{num & (2**bits-1):0{bits}b}"


# 创建客户端
client = ModbusTcpClient("192.168.0.100", port=502)
client.connect()

try:
    header_response = client.read_input_registers(RegisterAddress.Input.Header, count=2)
    print(header_response.registers)
finally:
    client.close()
