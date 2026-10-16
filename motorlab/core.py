"""幅值不变 Clarke 变换；所有转子参数折算到定子侧，单位为 SI。"""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Parameters:
    rs: float = 1.4
    rr: float = 1.0
    lm: float = 0.17
    ls: float = 0.18
    lr: float = 0.18
    poles: int = 2  # 极对数
    inertia: float = 0.04
    friction: float = 0.002


@dataclass(frozen=True)
class Sample:
    """辨识器唯一输入接口，无真实电阻、磁链或负载。"""
    voltage: np.ndarray
    current: np.ndarray
    speed: float
    time: float = 0.0


def electrical(x, voltage, speed, rr, p):
    """x=[iα,iβ,ψrα,ψrβ]；静止 αβ 坐标系。"""
    current, flux = x[:2], x[2:4]
    leakage = p.ls - p.lm**2 / p.lr
    rotation = np.array([-flux[1], flux[0]])
    dflux = rr / p.lr * (p.lm * current - flux) + p.poles * speed * rotation
    dcurrent = (voltage - p.rs * current - p.lm / p.lr * dflux) / leakage
    return np.r_[dcurrent, dflux]


def torque(x, p):
    return 1.5 * p.poles * p.lm / p.lr * (x[2] * x[1] - x[3] * x[0])


class Motor:
    def __init__(self, p):
        self.p = p
        self.state = np.zeros(5)

    def step(self, voltage, load, rr, dt):
        def rhs(x):
            mechanical = (torque(x, self.p) - load - self.p.friction*x[4])/self.p.inertia
            return np.r_[electrical(x[:4], voltage, x[4], rr, self.p), mechanical]
        x = self.state
        k1 = rhs(x)
        k2 = rhs(x + dt*k1/2)
        k3 = rhs(x + dt*k2/2)
        k4 = rhs(x + dt*k3)
        self.state = x + dt*(k1 + 2*k2 + 2*k3 + k4)/6


class Sensors:
    def __init__(self, seed=7, current_noise=.02, voltage_noise=.05,
                 speed_noise=.05, current_bias=0., voltage_bias=0.,
                 adc_bits=0, current_range=25., voltage_range=400.):
        self.rng = np.random.default_rng(seed)
        self.current_noise = current_noise
        self.voltage_noise = voltage_noise
        self.speed_noise = speed_noise
        self.current_bias = current_bias
        self.voltage_bias = voltage_bias
        self.adc_bits = adc_bits
        self.current_range = current_range
        self.voltage_range = voltage_range

    def _adc(self, value, span):
        value = np.clip(value, -span, span)
        if self.adc_bits:
            quantum = 2*span/(2**self.adc_bits-1)
            value = np.round((value+span)/quantum)*quantum-span
        return value

    def sample(self, voltage, state, time=0.):
        # αβ 域等效传感器；零偏分别作用于两个分量，非三相 ADC 电路模型。
        u = self._adc(voltage + self.voltage_bias + self.rng.normal(0, self.voltage_noise, 2), self.voltage_range)
        i = self._adc(state[:2] + self.current_bias + self.rng.normal(0, self.current_noise, 2), self.current_range)
        return Sample(u, i, float(state[4] + self.rng.normal(0, self.speed_noise)), float(time))


class ResistanceEKF:
    """增广状态 [iα,iβ,ψrα,ψrβ,Rr]；不接收 Motor 对象。"""
    def __init__(self, p, initial_rr=.65, current_noise=.02):
        self.p = p
        self.x = np.array([0., 0., 0., 0., initial_rr])
        self.cov = np.diag([.1, .1, .01, .01, .25])
        self.h = np.eye(5)[:2]
        self.r = np.eye(2)*max(current_noise, .005)**2
        self.last_innovation = np.zeros(2)
        self.previous_speed = None

    def _rhs_jacobian(self, x, voltage, speed):
        """连续模型与解析雅可比；不对真实模型取数，不做数值差分。"""
        p = self.p
        leakage = p.ls-p.lm*p.lm/p.lr
        coupling = p.lm/p.lr
        a = x[4]/p.lr
        w = p.poles*speed
        rotation = np.array([[0., -1.], [1., 0.]])
        identity = np.eye(2)
        rotor = -a*identity+w*rotation
        jac = np.zeros((5, 5))
        jac[:2, :2] = -(p.rs+coupling*a*p.lm)/leakage*identity
        jac[:2, 2:4] = -coupling/leakage*rotor
        jac[2:4, :2] = a*p.lm*identity
        jac[2:4, 2:4] = rotor
        derivative = (p.lm*x[:2]-x[2:4])/p.lr
        jac[2:4, 4] = derivative
        jac[:2, 4] = -coupling/leakage*derivative
        rhs = np.zeros(5)
        rhs[:4] = jac[:4, :4] @ x[:4]
        rhs[:2] += voltage/leakage
        return rhs, jac

    def _transition(self, x, voltage, speed, dt):
        """RK4 状态和离散雅可比一起积分；采样周期独立于被测电机子步长。"""
        identity = np.eye(5)
        k1, a1 = self._rhs_jacobian(x, voltage, speed)
        k2, a2 = self._rhs_jacobian(x+dt*k1/2, voltage, speed)
        j2 = a2 @ (identity+dt*a1/2)
        k3, a3 = self._rhs_jacobian(x+dt*k2/2, voltage, speed)
        j3 = a3 @ (identity+dt*j2/2)
        k4, a4 = self._rhs_jacobian(x+dt*k3, voltage, speed)
        j4 = a4 @ (identity+dt*j3)
        return (x+dt*(k1+2*k2+2*k3+k4)/6,
                identity+dt*(a1+2*j2+2*j3+j4)/6)

    def update(self, sample, dt):
        speed = sample.speed if self.previous_speed is None else (sample.speed+self.previous_speed)/2
        self.previous_speed = sample.speed
        predicted, jacobian = self._transition(self.x, sample.voltage, speed, dt)
        q = np.diag([.02, .02, 1e-6, 1e-6, .003])*dt
        prior = jacobian @ self.cov @ jacobian.T + q
        innovation = sample.current - self.h @ predicted
        s = self.h @ prior @ self.h.T + self.r
        gain = np.linalg.solve(s, self.h @ prior).T
        self.x = predicted + gain @ innovation
        # 投影到教学实验允许的物理范围；触边不能作为收敛证据。
        self.x[4] = np.clip(self.x[4], .1, 3.)
        residual = np.eye(5) - gain @ self.h
        self.cov = residual @ prior @ residual.T + gain @ self.r @ gain.T
        self.last_innovation = innovation
        return float(self.x[4])
