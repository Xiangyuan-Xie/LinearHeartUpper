import numpy as np
from pymodbus.client import ModbusTcpClient

from common import RegisterAddress
from communication import float_to_fixed, fixed_to_float


def fixed_bin(num, bits=16):
    return f"0b{num & (2**bits-1):0{bits}b}"

# 创建客户端
client = ModbusTcpClient('192.168.0.100', port=502)
client.connect()

try:
    # response = client.read_input_registers(address=0, count=1)
    # print(response)

    # print(client.write_coil(RegisterAddress.Coil.PowerOn, False))
    # print(client.write_coil(RegisterAddress.Coil.PowerOff, True))
    # print(client.write_coil(RegisterAddress.Coil.Reset, False))
    # print(client.write_coil(RegisterAddress.Coil.Start, False))
    # print(client.write_coil(RegisterAddress.Coil.Stop, False))

    print(client.read_coils(RegisterAddress.Coil.PowerOn))
    print(client.read_coils(RegisterAddress.Coil.PowerOff))
    print(client.read_coils(RegisterAddress.Coil.Reset))
    print(client.read_coils(RegisterAddress.Coil.Start))
    print(client.read_coils(RegisterAddress.Coil.Stop))

    # packet = float_to_fixed(np.array([1]), byte_order='>')
    # print(fixed_bin(packet[0]), fixed_bin(packet[1]))
    # response = client.write_registers(address=2, values=packet.tolist())
    # response = client.write_registers(address=0, values=[1, 1])
finally:
    client.close()