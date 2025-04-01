from pymodbus import ModbusException
from pymodbus.client import ModbusTcpClient

# 创建客户端
client = ModbusTcpClient('127.0.0.1', port=502)
client.connect()

try:
    response = client.write_registers(address=0x2000, values=[1, 2, 3])
    if response is None:
        print("写入失败（无响应）")
    elif response.isError():
        print(f"服务器返回错误：{response}")
    else:
        print(f"写入成功，起始地址{response.address} ，数量{response.count}")
except ModbusException as e:
    print(f"Modbus异常：{e}")
except Exception as e:
    print(f"未知错误：{e}")
finally:
    client.close()