"""中心对齐 SVPWM：零序注入占空比与七段式六开关理想逆变器。

载波从周期边界的1下降至中点0，再升回1。精确分割门极切换时刻，
因此不会因机械/控制积分步长偏大而漏掉窄脉冲。没有死区和器件压降。
"""
from array import array
from bisect import bisect_left, bisect_right
import math

SQRT3 = math.sqrt(3.)


def inverse_clarke(vector):
    a, b = vector
    return (float(a), float(-.5*a+SQRT3*.5*b), float(-.5*a-SQRT3*.5*b))


def bridge_voltage(gates, dc_bus):
    """无中性线星接负载：相对浮动中性点电压与 αβ 电压。"""
    a, b, c = gates
    common = (a+b+c)/3.
    phases = (dc_bus*(a-common), dc_bus*(b-common), dc_bus*(c-common))
    alpha = (2./3.)*dc_bus*(a-.5*b-.5*c)
    beta = dc_bus/SQRT3*(b-c)
    return phases, (alpha, beta)


class SVPWM:
    def __init__(self, frequency, dc_bus):
        self.frequency, self.dc_bus = frequency, dc_bus
        self.period = 1./frequency
        self.duty = (.5, .5, .5)
        self.zero_sequence = 0.
        self.sector = 1
        self.t1, self.t2, self.t0 = 0., 0., self.period
        self.command = (0., 0.)

    def set_command(self, voltage):
        self.command = tuple(float(v) for v in voltage)
        phases = inverse_clarke(voltage)
        self.zero_sequence = -.5*(max(phases)+min(phases))
        raw = tuple(.5+(v+self.zero_sequence)/self.dc_bus for v in phases)
        if min(raw) < -1e-9 or max(raw) > 1+1e-9:
            raise ValueError('SVPWM 指令超出线性调制范围；请检查电压矢量限幅')
        self.duty = tuple(min(1., max(0., v)) for v in raw)
        angle = math.atan2(voltage[1], voltage[0])%(2*math.pi)
        self.sector = min(6, int(angle/(math.pi/3))+1)
        inside = angle-(self.sector-1)*math.pi/3
        scale = SQRT3*self.period*math.hypot(*voltage)/self.dc_bus
        self.t1 = scale*math.sin(math.pi/3-inside)
        self.t2 = scale*math.sin(inside)
        self.t0 = max(0., self.period-self.t1-self.t2)

    def carrier(self, time):
        phase = (time*self.frequency)%1.
        return abs(2*phase-1.)

    def segments(self, start, end):
        """返回本控制保持区间中精确门极事件段 (起点,终点,上桥臂状态)。"""
        period = self.period
        first_cycle = math.floor((start+period*1e-9)/period)
        last_cycle = math.ceil((end-period*1e-9)/period)
        local = sorted({0., period/2, period, *[(1-d)*period/2 for d in self.duty],
                        *[(1+d)*period/2 for d in self.duty]})
        for cycle in range(first_cycle, last_cycle):
            origin = cycle*period
            for left, right in zip(local, local[1:]):
                a, b = max(start, origin+left), min(end, origin+right)
                if b-a < 1e-13:
                    continue
                carrier = self.carrier((a+b)/2)
                yield a, b, tuple(int(d >= carrier) for d in self.duty)

    def telemetry(self):
        return dict(duty_a=self.duty[0], duty_b=self.duty[1], duty_c=self.duty[2],
                    modulation_a=2*self.duty[0]-1, modulation_b=2*self.duty[1]-1,
                    modulation_c=2*self.duty[2]-1, zero_sequence=self.zero_sequence,
                    pwm_sector=self.sector, pwm_t1=self.t1, pwm_t2=self.t2, pwm_t0=self.t0,
                    pwm_period=self.period, pwm_frequency=self.frequency)


WAVE_KEYS = ('time', 'carrier', 'duty_a', 'duty_b', 'duty_c',
             'gate_au', 'gate_al', 'gate_bu', 'gate_bl', 'gate_cu', 'gate_cl',
             'v_a', 'v_b', 'v_c', 'u_alpha_switch', 'u_beta_switch',
             'i_a', 'i_b', 'i_c', 'rotor_angle')


class SwitchingTrace:
    """扁平双精度缓冲保存整个实验；只按所选毫秒窗口传输到浏览器。"""
    def __init__(self):
        self.data = array('d')
        self.times = array('d')

    def append(self, time, pwm, gates, phases, voltage, current, angle):
        ia, ib, ic = inverse_clarke(current)
        a, b, c = gates
        values = (time, pwm.carrier(time), *pwm.duty, a, 1-a, b, 1-b, c, 1-c,
                  *phases, *voltage, ia, ib, ic, angle)
        self.data.extend(values)
        self.times.append(time)

    def window(self, start, end, max_rows=20000):
        left = max(0, bisect_left(self.times, start)-1)
        right = min(len(self.times), bisect_right(self.times, end)+1)
        if right-left > max_rows:
            raise ValueError('高频窗口过大，请缩短至更少 PWM 周期；完整数据可用 CSV 导出')
        width = len(WAVE_KEYS)
        # 不抽稀门极边沿，避免把不存在的开关波形画出来。
        return [list(self.data[i*width:(i+1)*width]) for i in range(left, right)]

    def rows(self):
        width = len(WAVE_KEYS)
        for i in range(len(self.times)):
            yield self.data[i*width:(i+1)*width]

    def __len__(self):
        return len(self.times)
