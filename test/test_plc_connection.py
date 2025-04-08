import numpy as np
from pymodbus.client import ModbusTcpClient

from communication import float_to_fixed, fixed_to_float


def fixed_bin(num, bits=16):
    return f"0b{num & (2**bits-1):0{bits}b}"

# 创建客户端
client = ModbusTcpClient('192.168.0.100', port=502)
client.connect()

try:
    result = client.read_input_registers(address=0, count=2)
    print("read: ", result.registers)
    print(fixed_to_float(np.array(result.registers)))

    packet = float_to_fixed(np.array([234.56789]))
    print(fixed_bin(packet[0]), fixed_bin(packet[1]))
    response = client.write_registers(address=0, values=packet.tolist())
except Exception as e:
    print(e)
finally:
    client.close()