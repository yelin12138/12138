import unittest
import numpy as np
from motorlab.core import Parameters, Motor, ResistanceEKF, Sensors, electrical, torque


class PhysicsTests(unittest.TestCase):
    def test_unpowered_rest_remains_at_rest(self):
        motor = Motor(Parameters())
        motor.step(np.zeros(2), 0., 1., .0002)
        np.testing.assert_array_equal(motor.state, np.zeros(5))

    def test_power_balance(self):
        p = Parameters()
        x = np.array([2., -3., .12, .2])
        u = np.array([100., -70.])
        speed = 40.
        dx = electrical(x, u, speed, p.rr, p)
        leakage = p.ls-p.lm**2/p.lr
        ir = (x[2:]-p.lm*x[:2])/p.lr
        stored_power = 1.5*(leakage*np.dot(x[:2], dx[:2])+np.dot(x[2:], dx[2:])/p.lr)
        input_power = 1.5*np.dot(u, x[:2])
        copper_loss = 1.5*(p.rs*np.dot(x[:2], x[:2])+p.rr*np.dot(ir, ir))
        self.assertAlmostEqual(input_power, stored_power+copper_loss+torque(x, p)*speed, places=9)

    def test_estimator_has_no_truth_input(self):
        ekf = ResistanceEKF(Parameters())
        sample = Sensors().sample(np.zeros(2), np.zeros(5))
        value = ekf.update(sample, .0002)
        self.assertTrue(np.isfinite(value))
        self.assertGreater(np.linalg.eigvalsh(ekf.cov).min(), 0)


if __name__ == '__main__':
    unittest.main()
