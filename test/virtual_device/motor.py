import threading
import time
from collections import deque

import numpy as np

from logger import logger


class Motor:
    def __init__(self):
        self.current_pos = 0.0  # 当前绝对位置（mm）
        self.current_vel = 0.0  # 当前运动速度（mm/s）

        self.soft_limit_min = -2.0  # 软限位最小值（工艺保护）
        self.soft_limit_max = 70.0  # 软限位最大值
        self.hard_limit_min = -2.0  # 硬限位最小值（机械保护）
        self.hard_limit_max = 70.0  # 硬限位最大值
        self.safe_margin = 2.0  # 预判制动距离（mm）

        self.Kp = 2.5  # 比例系数
        self.Ki = 0.1  # 积分系数
        self.Kd = 0.4  # 微分系数
        self.integral = 0.0  # 积分累积
        self.prev_error = 0.0  # 前次误差

        self._target_pos = 0.0  # 当前目标位置
        self.max_vel = 50.0  # 最大允许速度
        self.control_interval = 0.001  # 控制周期1ms

        self.new_target_queue = deque()  # 目标队列（FIFO）
        self.is_running = False  # 运行状态标志
        self.control_thread = None  # 控制线程句柄

        self.data_buffer = {
            'time': deque(maxlen=60000),  # 60秒历史数据
            'pos': deque(maxlen=60000),
            'vel': deque(maxlen=60000),
            'target': deque(maxlen=60000)
        }

    def start(self):
        """
        系统启动
        """
        if not self._check_hard_limit(self.current_pos):
            raise RuntimeError(f"初始位置 {self.current_pos:.2f}mm 超出硬限位！")
        if not self.is_running:
            self.is_running = True
            self.control_thread = threading.Thread(target=self._control_loop)
            self.control_thread.start()
            logger.info(f"系统启动, 初始位置 {self.current_pos:.2f}mm")

    def stop(self):
        """
        系统关闭
        """
        self.is_running = False
        if self.control_thread:
            self.control_thread.join()

    def update_target(self, new_target):
        """
        更新目标位置
        """
        if not (self.soft_limit_min <= new_target <= self.soft_limit_max):
            raise ValueError(f"目标位置超出软限位范围 [{self.soft_limit_min},  {self.soft_limit_max}]")
        self.new_target_queue.append(new_target)

    def _control_loop(self):
        """
        控制主循环
        """
        start_time = time.time()
        last_cycle = start_time

        while self.is_running:
            # 处理目标队列
            self._process_target()

            # PID计算
            control_signal = self._calculate_pid()

            # 状态更新与限位保护
            self._update_motion_state(control_signal)

            # 数据记录
            current_time = time.time() - start_time
            self._record_data(current_time)

            # 精确周期控制
            while (time.time() - last_cycle) < self.control_interval:
                time.sleep(0.00001)
            last_cycle += self.control_interval

    def _process_target(self):
        """
        处理目标队列
        """
        if self.new_target_queue:
            self._target_pos = self.new_target_queue.popleft()
        logger.debug(f"切换目标至：{self._target_pos}mm")

    def _calculate_pid(self):
        """
        PID计算
        """
        error = self._target_pos - self.current_pos

        # 积分项抗饱和
        self.integral += error * self.control_interval
        self.integral = np.clip(self.integral, -1000, 1000)  # 积分限幅

        # 微分项滤波
        derivative = (error - self.prev_error) / self.control_interval
        self.prev_error = error

        # 计算控制量
        return self.Kp * error + self.Ki * self.integral + self.Kd * derivative

    def _update_motion_state(self, control_signal):
        """
        状态更新
        """
        # 预判下一周期位置
        req_vel = np.clip(control_signal, -self.max_vel, self.max_vel)
        predicted_pos = self.current_pos + req_vel * self.control_interval

        # 硬限位预判制动
        if not self._check_hard_limit(predicted_pos):
            req_vel = -self.max_vel * np.sign(req_vel)

            # 更新运动状态
        self.current_vel = req_vel
        self.current_pos += self.current_vel * self.control_interval

        # 硬限位最终保护
        if not self._check_hard_limit(self.current_pos):
            self.stop()
            raise RuntimeError("触发硬限位保护")

    def _check_hard_limit(self, pos):
        """
        硬限位检查
        """
        return self.hard_limit_min <= pos <= self.hard_limit_max

    def _record_data(self, t):
        """
        数据记录
        """
        self.data_buffer['time'].append(t)
        self.data_buffer['pos'].append(self.current_pos)
        self.data_buffer['vel'].append(self.current_vel)
        self.data_buffer['target'].append(self._target_pos)


if __name__ == "__main__":
    motor = Motor()
    motor.start()