"""间接转子磁场定向控制：速度 PI + d/q 电流 PI，输出待调制电压指令。"""
import math
import numpy as np


def park(vector, theta):
    c, s = math.cos(theta), math.sin(theta)
    return np.array([c*vector[0]+s*vector[1], -s*vector[0]+c*vector[1]])


def inverse_park(vector, theta):
    c, s = math.cos(theta), math.sin(theta)
    return np.array([c*vector[0]-s*vector[1], s*vector[0]+c*vector[1]])


class PI:
    """位置式 PI；积分器通过实际限幅输出回算，避免持续饱和积累。"""
    def __init__(self, kp, ki, tracking_rate):
        self.kp, self.ki, self.tracking_rate = kp, ki, tracking_rate
        self.integral = 0.
        self.p = 0.

    def output(self, error):
        self.p = self.kp*error
        return self.p+self.integral

    def integrate(self, error, applied, requested, dt):
        self.integral += dt*(self.ki*error+self.tracking_rate*(applied-requested))


class FOCController:
    """仅接收传感器样本和控制用参数；没有 Motor/真实磁链接口。"""
    def __init__(self, parameters, config):
        self.p, self.config = parameters, config
        leakage = parameters.ls-parameters.lm**2/parameters.lr
        bandwidth = 2*math.pi*config['current_bandwidth_hz']
        self.speed_pi = PI(config['speed_kp'], config['speed_ki'], 15.)
        self.d_pi = PI(leakage*bandwidth, parameters.rs*bandwidth, bandwidth)
        self.q_pi = PI(leakage*bandwidth, parameters.rs*bandwidth, bandwidth)
        self.theta = 0.
        self.flux = 0.
        self.last = {}

    def update(self, sample, time, dt, rr_control):
        p, c = self.p, self.config
        control_theta = self.theta
        id_measured, iq_measured = park(sample.current, self.theta)
        id_ref = c['id_ref']*min(1., time/.12)
        speed_fraction = np.clip((time-c['magnetization_time'])/c['speed_ramp_time'], 0., 1.)
        speed_ref = c['target_rpm']*2*math.pi/60*speed_fraction
        speed_error = speed_ref-sample.speed
        iq_limit = math.sqrt(max(c['current_limit']**2-id_ref**2, 0.))
        iq_requested = self.speed_pi.output(speed_error)
        iq_ref = float(np.clip(iq_requested, -iq_limit, iq_limit)) if time >= c['magnetization_time'] else 0.
        speed_integral = self.speed_pi.integral
        self.speed_pi.integrate(speed_error, iq_ref, iq_requested, dt)
        dflux = rr_control/p.lr*(p.lm*id_measured-self.flux)
        self.flux = max(0., self.flux+dt*dflux)
        slip = rr_control*p.lm/p.lr*iq_measured/max(self.flux, .08) if time >= .12 else 0.
        omega_e = p.poles*sample.speed+slip
        id_error, iq_error = id_ref-id_measured, iq_ref-iq_measured
        vd_pi, vq_pi = self.d_pi.output(id_error), self.q_pi.output(iq_error)
        d_integral, q_integral = self.d_pi.integral, self.q_pi.integral
        leakage = p.ls-p.lm**2/p.lr
        vd_ff = -omega_e*leakage*iq_measured+p.lm/p.lr*dflux
        vq_ff = omega_e*(leakage*id_measured+p.lm/p.lr*self.flux)
        requested = np.array([vd_pi+vd_ff, vq_pi+vq_ff])
        magnitude = float(np.linalg.norm(requested))
        voltage_limit = c['dc_bus_voltage']/math.sqrt(3.)
        factor = min(1., voltage_limit/max(magnitude, 1e-12))
        applied = requested*factor
        self.d_pi.integrate(id_error, applied[0]-vd_ff, vd_pi, dt)
        self.q_pi.integrate(iq_error, applied[1]-vq_ff, vq_pi, dt)
        # αβ 电压指令在采样区间保持；实际开关电压由 SVPWM 生成。
        # 使用区间中点角度逆变换；平均逆变器对照模式才直接施加该指令。
        voltage_theta = self.theta+omega_e*dt/2
        voltage = inverse_park(applied, voltage_theta)
        self.theta = (self.theta+omega_e*dt+math.pi)%(2*math.pi)-math.pi
        self.last = dict(speed_ref_rpm=speed_ref*60/(2*math.pi), speed_error=speed_error,
                         id=float(id_measured), iq=float(iq_measured), id_ref=id_ref, iq_ref=iq_ref,
                         id_error=id_error, iq_error=iq_error, speed_p=self.speed_pi.p,
                         speed_i=speed_integral, speed_unsat=iq_requested,
                         id_p=self.d_pi.p, id_i=d_integral, iq_p=self.q_pi.p, iq_i=q_integral,
                         vd_pi=vd_pi, vq_pi=vq_pi, vd_ff=vd_ff, vq_ff=vq_ff,
                         vd_unsat=float(requested[0]), vq_unsat=float(requested[1]),
                         vd=float(applied[0]), vq=float(applied[1]), theta=self.theta,
                         voltage_theta=voltage_theta, flux_est=self.flux, dflux_est=dflux,
                         slip=slip, omega_e=omega_e, voltage_limit=voltage_limit,
                         voltage_saturated=float(factor < 1.), current_limit=c['current_limit'],
                         iq_limit=iq_limit, rr_control=rr_control,
                         control_i_alpha=float(sample.current[0]), control_i_beta=float(sample.current[1]),
                         control_theta=control_theta, control_speed=sample.speed,
                         control_speed_rpm=sample.speed*60/(2*math.pi),
                         rotor_electrical_speed=p.poles*sample.speed,
                         control_sampled_at=sample.time)
        return voltage
