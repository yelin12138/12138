"""确定性、可暂停/单步的多速率仿真；真值只进入被测对象、评价和显式 oracle 模式。"""
from collections import deque
from dataclasses import replace
import math
import numpy as np
from .core import Parameters, Sample, Motor, Sensors, ResistanceEKF, torque, electrical
from .control import FOCController, park


DEFAULT_CONFIG = {
    'duration': 4., 'sample_time': .0005, 'plant_substeps': 2,
    'target_rpm': 1000., 'rr_initial': 1., 'rr_final': 1.3,
    'ramp_start': 1.4, 'ramp_end': 2.4,
    'load_initial': 0., 'load_final': 5., 'load_step': 2.8,
    'mode': 'fixed', 'seed': 7, 'initial_estimate': .65,
    'nominal_rr': 1., 'adaptation_start': 1., 'adaptation_tau': .15,
    'current_noise': .02, 'voltage_noise': .05, 'speed_noise': .05,
    'current_bias': 0., 'voltage_bias': 0., 'sensor_delay_steps': 0,
    'adc_bits': 0, 'current_range': 25., 'voltage_range': 400.,
    'dc_bus_voltage': 540., 'current_limit': 12., 'id_ref': 4.,
    'speed_kp': .32, 'speed_ki': 1.2, 'current_bandwidth_hz': 120.,
    'magnetization_time': .3, 'speed_ramp_time': .8,
}


def validate_config(config):
    unknown = set(config)-set(DEFAULT_CONFIG)
    if unknown:
        raise ValueError('未知配置项: '+', '.join(sorted(unknown)))
    result = {**DEFAULT_CONFIG, **config}
    for key, value in result.items():
        if key != 'mode' and (not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError(f'{key} 必须为有限数值')
    if result['mode'] not in ('fixed', 'adaptive', 'oracle'):
        raise ValueError('mode 必须为 fixed、adaptive 或 oracle')
    bounds = {'duration': (.01, 30.), 'sample_time': (.0001, .001), 'plant_substeps': (1, 20),
              'target_rpm': (0., 1500.), 'rr_initial': (.2, 2.5), 'rr_final': (.2, 2.5),
              'initial_estimate': (.1, 3.), 'nominal_rr': (.2, 2.5),
              'current_noise': (0., 2.), 'voltage_noise': (0., 10.), 'speed_noise': (0., 5.),
              'current_bias': (-2., 2.), 'voltage_bias': (-10., 10.),
              'sensor_delay_steps': (0, 20), 'adc_bits': (0, 24),
              'current_range': (1., 200.), 'voltage_range': (10., 1000.),
              'dc_bus_voltage': (100., 800.), 'current_limit': (2., 20.), 'id_ref': (.5, 8.),
              'speed_kp': (.001, 2.), 'speed_ki': (0., 10.), 'current_bandwidth_hz': (20., 250.),
              'magnetization_time': (.15, 5.), 'speed_ramp_time': (.1, 10.),
              'adaptation_tau': (.01, 5.), 'load_initial': (0., 15.), 'load_final': (0., 15.)}
    for key, (low, high) in bounds.items():
        if not low <= result[key] <= high:
            raise ValueError(f'{key} 必须在 [{low}, {high}] 范围内')
    for key in ('plant_substeps', 'sensor_delay_steps', 'adc_bits', 'seed'):
        if int(result[key]) != result[key] or result[key] < 0:
            raise ValueError(f'{key} 必须为非负整数')
        result[key] = int(result[key])
    for key in ('ramp_start', 'load_step', 'adaptation_start'):
        if result[key] < 0:
            raise ValueError(f'{key} 不得小于零')
    if result['ramp_end'] <= result['ramp_start']:
        raise ValueError('ramp_end 必须晚于 ramp_start')
    if result['id_ref'] >= result['current_limit']:
        raise ValueError('励磁电流须小于电流限幅')
    if result['duration']/result['sample_time'] > 100000:
        raise ValueError('一次实验最多 100000 个采样点')
    return result


class Simulation:
    def __init__(self, config=None):
        self.config = validate_config(config or {})
        c = self.config
        # 参数实例分离；变化电阻只在 plant.step 入参出现。
        self.parameters = Parameters(rr=c['nominal_rr'])
        self.plant = Motor(replace(self.parameters, rr=c['rr_initial']))
        self.sensor = Sensors(c['seed'], **{key: c[key] for key in (
            'current_noise', 'voltage_noise', 'speed_noise', 'current_bias', 'voltage_bias',
            'adc_bits', 'current_range', 'voltage_range')})
        self.estimator = ResistanceEKF(self.parameters, c['initial_estimate'], c['current_noise'])
        controller_config = {key: c[key] for key in (
            'current_bandwidth_hz', 'speed_kp', 'speed_ki', 'id_ref',
            'magnetization_time', 'speed_ramp_time', 'target_rpm',
            'current_limit', 'dc_bus_voltage')}
        self.controller = FOCController(self.parameters, controller_config)
        self.sample = self.sensor.sample(np.zeros(2), self.plant.state, 0.)
        self.queue = deque([self.sample]*(c['sensor_delay_steps']+1))
        self.estimator_time = 0.
        self.rr_control = c['nominal_rr']
        self.index = 0
        self.total_steps = int(math.ceil(c['duration']/c['sample_time']-1e-10))
        self.history = []
        self.controller.update(Sample(np.zeros(2), np.zeros(2), 0.), 0., 0., self.rr_control)
        self._initial_snapshot = self._record(np.zeros(2), 0., 0., c['sample_time'])

    @property
    def done(self):
        return self.index >= self.total_steps

    def _resistance(self, time):
        c = self.config
        fraction = np.clip((time-c['ramp_start'])/(c['ramp_end']-c['ramp_start']), 0., 1.)
        return float(c['rr_initial']+(c['rr_final']-c['rr_initial'])*fraction)

    def _load(self, time):
        c = self.config
        return c['load_initial'] if time < c['load_step'] else c['load_final']

    def step(self, count=1):
        if not isinstance(count, int) or count < 0 or count > 100000:
            raise ValueError('步数必须为 0 到 100000 之间的整数')
        output = []
        c = self.config
        for _ in range(min(count, self.total_steps-self.index)):
            start = self.index*c['sample_time']
            dt = min(c['sample_time'], c['duration']-start)
            if c['mode'] == 'oracle':
                self.rr_control = self._resistance(start)
            elif c['mode'] == 'adaptive' and start >= c['adaptation_start']:
                weight = 1-math.exp(-dt/c['adaptation_tau'])
                self.rr_control += weight*(float(self.estimator.x[4])-self.rr_control)
            voltage = self.controller.update(self.sample, start, dt, self.rr_control)
            subdt = dt/c['plant_substeps']
            for substep in range(c['plant_substeps']):
                middle = start+(substep+.5)*subdt
                self.plant.step(voltage, self._load(middle), self._resistance(middle), subdt)
            end = start+dt
            if not np.all(np.isfinite(self.plant.state)) or np.max(np.abs(self.plant.state)) > 1e5:
                raise RuntimeError('数值状态失稳；请减小采样间隔、控制带宽或恢复默认参数')
            newest = self.sensor.sample(voltage, self.plant.state, end)
            self.queue.append(newest)
            self.queue.popleft()
            self.sample = self.queue[0]
            if self.sample.time > self.estimator_time+1e-12:
                self.estimator.update(self.sample, self.sample.time-self.estimator_time)
                self.estimator_time = self.sample.time
            self.index += 1
            row = self._record(voltage, start, end, dt)
            self.history.append(row)
            output.append(row)
        return output

    def _record(self, voltage, start, end, dt):
        """评价器是唯一读取真实磁链和真实电阻以打分的路径。"""
        p, c, x = self.parameters, self.config, self.plant.state
        rr_true = self._resistance(end)
        rr_at_estimate = self._resistance(self.estimator_time)
        rr_est = float(self.estimator.x[4])
        flux_d, flux_q = park(x[2:4], self.controller.theta)
        measured_id, measured_iq = park(self.sample.current, self.controller.theta)
        derivative = electrical(x[:4], voltage, x[4], rr_true, p)
        load = self._load(end)
        estimate_error = rr_est-rr_true
        row = dict(self.controller.last)
        row.update(time=end, sample_index=self.index, sample_time=dt,
                   integration_step=dt/c['plant_substeps'], sampled_at=self.sample.time,
                   estimate_time=self.estimator_time, control_start=start, control_end=end,
                   sensor_delay=end-self.sample.time,
                   speed_rpm=self.sample.speed*60/(2*math.pi), speed_true_rpm=x[4]*60/(2*math.pi),
                   speed_measured=self.sample.speed, speed_true=x[4],
                   u_alpha=voltage[0], u_beta=voltage[1],
                   u_alpha_measured=self.sample.voltage[0], u_beta_measured=self.sample.voltage[1],
                   i_alpha=self.sample.current[0], i_beta=self.sample.current[1],
                   i_alpha_true=x[0], i_beta_true=x[1],
                   id_sample=measured_id, iq_sample=measured_iq,
                   rr_true=rr_true, rr_est=rr_est, rr_error_pct=100*abs(estimate_error)/rr_true,
                   rr_true_at_estimate=rr_at_estimate,
                   rr_aligned_error_pct=100*abs(rr_est-rr_at_estimate)/rr_at_estimate,
                   rr_signed_error=estimate_error, rr_std=np.sqrt(max(self.estimator.cov[4, 4], 0.)),
                   innovation=np.linalg.norm(self.estimator.last_innovation),
                   innovation_alpha=self.estimator.last_innovation[0], innovation_beta=self.estimator.last_innovation[1],
                   i_alpha_est=self.estimator.x[0], i_beta_est=self.estimator.x[1],
                   flux_alpha_est=self.estimator.x[2], flux_beta_est=self.estimator.x[3],
                   flux_alpha_true=x[2], flux_beta_true=x[3],
                   flux_d_true=flux_d, flux_q_true=flux_q,
                   flux_angle_error_deg=math.degrees(math.atan2(flux_q, flux_d)),
                   flux_true=np.linalg.norm(x[2:4]), torque=torque(x, p), load=load,
                   friction_torque=p.friction*x[4], acceleration=(torque(x,p)-load-p.friction*x[4])/p.inertia,
                   di_alpha=derivative[0], di_beta=derivative[1],
                   dflux_alpha=derivative[2], dflux_beta=derivative[3],
                   current_magnitude=np.linalg.norm(self.sample.current),
                   voltage_magnitude=np.linalg.norm(voltage),
                   speed_error_rpm=row['speed_ref_rpm']-self.sample.speed*60/(2*math.pi))
        return {key: float(value) for key, value in row.items()}

    def snapshot(self):
        if self.history:
            return dict(self.history[-1])
        return dict(self._initial_snapshot)

    def metrics(self):
        if not self.history:
            return {'samples': 0, 'completed': False}
        tail_start = max(0., self.history[-1]['time']-.4)
        tail = [row for row in self.history if row['time'] >= tail_start]
        def rms(rows, key):
            return float(np.sqrt(np.mean([row[key]**2 for row in rows])))
        return dict(samples=len(self.history), completed=self.done,
                    duration=self.history[-1]['time'],
                    tail_relative_mae_percent=float(np.mean([r['rr_error_pct'] for r in tail])),
                    tail_aligned_relative_mae_percent=float(np.mean([r['rr_aligned_error_pct'] for r in tail])),
                    full_rmse_ohm=rms(self.history, 'rr_signed_error'),
                    tail_speed_rmse_rpm=rms(tail, 'speed_error_rpm'),
                    tail_flux_angle_rms_deg=rms(tail, 'flux_angle_error_deg'),
                    peak_current_a=max(r['current_magnitude'] for r in self.history),
                    voltage_saturation_percent=100*float(np.mean([r['voltage_saturated'] for r in self.history])),
                    final_rr_est=self.history[-1]['rr_est'], final_rr_true=self.history[-1]['rr_true'],
                    mode=self.config['mode'], tail_window_seconds=min(.4, self.history[-1]['time']),
                    note='仿真评价；rr_error_pct 含采样延迟影响，rr_aligned_error_pct 按估计时间对齐。末段误差不是全工况精度，EKF 协方差不是经标定的置信保证。')
