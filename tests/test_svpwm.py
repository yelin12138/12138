"""开关事件、电压伏秒、参数约束及机械角度的独立验证。"""
import math
import unittest
import numpy as np
from motorlab.core import Motor, Parameters, electrical, torque
from motorlab.inverter import SVPWM, bridge_voltage, WAVE_KEYS
from motorlab.simulation import Simulation, validate_config


class SwitchingTests(unittest.TestCase):
    def test_all_sectors_volt_seconds_and_gate_adjacency(self):
        pwm = SVPWM(4000., 540.)
        for sector in range(1, 7):
            for within in (.13, .71):
                angle = (sector-1)*math.pi/3+within
                command = 220*np.array([math.cos(angle), math.sin(angle)])
                pwm.set_command(command)
                segments = list(pwm.segments(0., pwm.period))
                average = np.zeros(2)
                last = None
                for a, b, gates in segments:
                    phases, ab = bridge_voltage(gates, 540.)
                    self.assertAlmostEqual(sum(phases), 0., places=10)
                    average += np.array(ab)*(b-a)/pwm.period
                    if last is not None:
                        self.assertLessEqual(sum(abs(x-y) for x, y in zip(last, gates)), 1)
                    last = gates
                np.testing.assert_allclose(average, command, atol=1e-10)
                self.assertEqual(pwm.sector, sector)
                self.assertAlmostEqual(pwm.t1+pwm.t2+pwm.t0, pwm.period)
                self.assertGreaterEqual(pwm.t0, 0.)

    def test_zero_vectors_and_voltage_levels(self):
        for bits in range(8):
            gates = tuple((bits >> i)&1 for i in range(3))
            phases, ab = bridge_voltage(gates, 540.)
            for value in phases:
                self.assertAlmostEqual(value/180., round(value/180.))
            if bits in (0, 7):
                np.testing.assert_array_equal(ab, [0., 0.])

    def test_pulses_not_lost_in_coarse_requested_integration(self):
        sim = Simulation({'duration': .02, 'integration_max_step': .001, 'plant_substeps': 1})
        sim.step(sim.total_steps)
        wave = np.array(sim.switching.rows().__iter__().__next__())
        self.assertEqual(len(wave), len(WAVE_KEYS))
        records = sim.switching.window(0., .002)
        keys = {key: i for i, key in enumerate(WAVE_KEYS)}
        self.assertGreater(len(records), 60)
        self.assertTrue(any(r[keys['gate_au']] != records[0][keys['gate_au']] for r in records))
        for record in records:
            self.assertEqual(record[keys['gate_au']]+record[keys['gate_al']], 1)
            self.assertEqual(record[keys['gate_bu']]+record[keys['gate_bl']], 1)
            self.assertEqual(record[keys['gate_cu']]+record[keys['gate_cl']], 1)
            self.assertAlmostEqual(sum(record[keys[key]] for key in ['i_a','i_b','i_c']), 0.)
        for record in sim.history:
            np.testing.assert_allclose([record['u_alpha'],record['u_beta']],
                                       [record['u_alpha_command'],record['u_beta_command']], atol=1e-9)

    def test_motor_scalar_rk4_matches_independent_vector_equations(self):
        p = Parameters()
        motor = Motor(p)
        motor.state = np.array([2., -1., .3, .2, 70.])
        original = motor.state.copy()
        u, load, rr, dt = np.array([80., -30.]), 3., 1.2, .000025
        def rhs(x):
            return np.r_[electrical(x[:4],u,x[4],rr,p),
                         (torque(x,p)-load-p.friction*x[4])/p.inertia, x[4]]
        x = np.r_[original, 0.]
        k1=rhs(x); k2=rhs(x+dt*k1/2); k3=rhs(x+dt*k2/2); k4=rhs(x+dt*k3)
        expected=x+dt*(k1+2*k2+2*k3+k4)/6
        motor.step(u, load, rr, dt)
        np.testing.assert_allclose(np.r_[motor.state,motor.rotor_angle], expected, atol=1e-13)

    def test_motor_parameters_are_applied_and_invalid_lm_rejected(self):
        sim=Simulation({'motor_rs':2.,'motor_ls':.2,'motor_inertia':.08,'motor_poles':3})
        self.assertEqual(sim.plant.p.rs,2.)
        self.assertEqual(sim.controller.p.poles,3)
        self.assertEqual(sim.estimator.p.ls,.2)
        self.assertEqual(sim.plant.p.inertia,.08)
        self.assertAlmostEqual(sim.controller.d_pi.kp,
                               (.2-.17**2/.18)*2*math.pi*sim.config['current_bandwidth_hz'])
        for bad in [{'motor_lm':.2},{'motor_inertia':0.},{'motor_poles':1.5},
                    {'pwm_frequency':4000.,'sample_time':.0003},
                    {'sample_time':.0001,'pwm_frequency':4000.}]:
            with self.assertRaises(ValueError):validate_config(bad)

    def test_switching_integration_step_converges_at_fixed_sample_time(self):
        results=[]
        for h in [.0001,.00005,.000025]:
            sim=Simulation({'duration':.15,'integration_max_step':h,
                            'current_noise':0.,'voltage_noise':0.,'speed_noise':0.})
            sim.step(sim.total_steps)
            results.append(np.r_[sim.plant.state,sim.plant.rotor_angle])
        coarse=np.linalg.norm(results[0]-results[2]);fine=np.linalg.norm(results[1]-results[2])
        self.assertLess(fine,coarse)
        self.assertLess(coarse,1e-4)


if __name__=='__main__':unittest.main()
