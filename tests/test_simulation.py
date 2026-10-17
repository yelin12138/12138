"""物理/离散化/信号边界验证，而非界面实现快照。"""
import json
import unittest
import numpy as np
from motorlab.core import Parameters, Sample, ResistanceEKF
from motorlab.control import PI, park, inverse_park
from motorlab.simulation import Simulation, validate_config


class SimulationTests(unittest.TestCase):
    def test_park_transform_preserves_norm_and_round_trip(self):
        source = np.array([3.4, -5.2])
        for theta in [0., .3, -1.5, 3.14]:
            transformed = park(source, theta)
            np.testing.assert_allclose(np.linalg.norm(transformed), np.linalg.norm(source))
            np.testing.assert_allclose(inverse_park(transformed, theta), source)

    def test_discrete_ekf_jacobian_matches_perturbation(self):
        ekf = ResistanceEKF(Parameters())
        state = np.array([3., -2., .4, .2, 1.2])
        voltage = np.array([120., -40.])
        _, jac = ekf._transition(state, voltage, 105., .0005)
        numerical = np.empty((5, 5))
        for column in range(5):
            delta = np.eye(5)[column]*1e-6
            upper, _ = ekf._transition(state+delta, voltage, 105., .0005)
            lower, _ = ekf._transition(state-delta, voltage, 105., .0005)
            numerical[:, column] = (upper-lower)/2e-6
        np.testing.assert_allclose(jac, numerical, rtol=1e-6, atol=1e-8)

    def test_live_transform_probes_use_same_sample_and_angle(self):
        sim = Simulation({'duration': .5, 'sensor_delay_steps': 1})
        sim.step(sim.total_steps)
        for row in sim.history[::23]:
            dq = park([row['control_i_alpha'], row['control_i_beta']], row['control_theta'])
            np.testing.assert_allclose(dq, [row['id'], row['iq']], atol=1e-12)
            voltage = inverse_park([row['vd'], row['vq']], row['voltage_theta'])
            np.testing.assert_allclose(voltage, [row['u_alpha'], row['u_beta']], atol=1e-12)
            self.assertAlmostEqual(row['omega_e'], row['rotor_electrical_speed']+row['slip'])
            self.assertAlmostEqual(row['speed_error'],
                row['speed_ref_rpm']*2*np.pi/60-row['control_speed'])

    def test_estimator_uses_sample_not_parameter_truth(self):
        # rr 字段故意不同；预测方程必须仅使用自身增广估计电阻。
        first = ResistanceEKF(Parameters(rr=.2))
        second = ResistanceEKF(Parameters(rr=2.5))
        for k in range(20):
            sample = Sample(np.array([20., -10.]), np.array([.1*k, -.05*k]), 20.)
            self.assertEqual(first.update(sample, .0005), second.update(sample, .0005))
        self.assertFalse(hasattr(first, 'plant'))
        self.assertEqual(set(Sample.__dataclass_fields__), {'voltage', 'current', 'speed', 'time'})
        sim = Simulation({'rr_initial': 1.7, 'rr_final': 2.})
        self.assertNotIn('rr_initial', sim.controller.config)
        self.assertNotIn('rr_final', sim.controller.config)
        self.assertEqual(sim.controller.p.rr, 1.)

    def test_antiwindup_unwinds_saturated_integral(self):
        pi = PI(1., 2., 20.)
        for _ in range(1000):
            requested = pi.output(10.)
            pi.integrate(10., 1., requested, .001)
        self.assertLess(abs(pi.integral), 10.)
        requested = pi.output(0.)
        before = abs(pi.integral)
        for _ in range(200):
            requested = pi.output(0.)
            pi.integrate(0., np.clip(requested, -1., 1.), requested, .001)
        self.assertLess(abs(pi.integral), before)

    def test_foc_and_resistance_estimation(self):
        sim = Simulation()
        sim.step(sim.total_steps)
        metrics = sim.metrics()
        self.assertTrue(sim.done)
        self.assertLess(metrics['tail_relative_mae_percent'], 3.)
        self.assertLess(metrics['tail_speed_rmse_rpm'], 5.)
        self.assertLess(metrics['peak_current_a'], 15.)
        self.assertGreater(metrics['tail_flux_angle_rms_deg'], 3.)
        self.assertGreater(np.linalg.eigvalsh(sim.estimator.cov).min(), 0.)
        json.dumps(sim.history, allow_nan=False)
        adaptive = Simulation({'mode': 'adaptive'})
        adaptive.step(adaptive.total_steps)
        # 验证补偿的实际目标：减小磁场定向偏差，而非预设速度一定改善。
        self.assertLess(adaptive.metrics()['tail_flux_angle_rms_deg'],
                        metrics['tail_flux_angle_rms_deg']/3)
        self.assertLess(adaptive.metrics()['tail_flux_angle_rms_deg'], 1.)

    def test_plant_substep_convergence_at_fixed_sampling(self):
        common = dict(duration=1.2, current_noise=0., voltage_noise=0., speed_noise=0.,
                      inverter_model='average', integration_max_step=.001)
        simulations = [Simulation({**common, 'plant_substeps': count}) for count in (1, 2, 4)]
        for sim in simulations:
            sim.step(sim.total_steps)
        values = [np.array([r['speed_true_rpm'], r['rr_est']]) for r in
                  [sim.snapshot() for sim in simulations]]
        error_coarse = np.linalg.norm(values[0]-values[2])
        error_fine = np.linalg.norm(values[1]-values[2])
        self.assertLess(error_fine, error_coarse)
        self.assertLess(error_coarse, .005)

    def test_pause_single_step_and_delay_timestamps(self):
        sim = Simulation({'duration': .01, 'sensor_delay_steps': 3,
                          'ramp_start': 0., 'ramp_end': .02})
        initial = sim.snapshot()
        self.assertEqual(initial, sim.snapshot())
        rows = sim.step(5)
        self.assertEqual(set(initial), set(rows[-1]))
        self.assertAlmostEqual(rows[-1]['time']-rows[-1]['sampled_at'], .0015)
        self.assertEqual(rows[-1]['estimate_time'], rows[-1]['sampled_at'])
        self.assertLess(rows[-1]['rr_true_at_estimate'], rows[-1]['rr_true'])
        self.assertAlmostEqual(rows[-1]['rr_aligned_error_pct'],
            100*abs(rows[-1]['rr_est']-rows[-1]['rr_true_at_estimate'])/rows[-1]['rr_true_at_estimate'])
        self.assertAlmostEqual(rows[-1]['control_end']-rows[-1]['control_start'], .0005)
        self.assertEqual(len(sim.history), 5)
        self.assertEqual(sim.step(0), [])

    def test_configuration_rejects_unsafe_or_ambiguous_values(self):
        for bad in ({'sample_time': 0.}, {'duration': float('nan')}, {'mode': 'unknown'},
                    {'plant_substeps': 1.5}, {'rr_initial': -1.}, {'ramp_end': 0.},
                    {'duration': 30., 'sample_time': .0001}, {'unknown': 1}):
            with self.assertRaises(ValueError):
                validate_config(bad)


if __name__ == '__main__':
    unittest.main()
