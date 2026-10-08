import unittest

from calibration import Calibration
from head_pose import HeadPoseEstimator, normalize_angle_degrees, unwrap_angle


class CalibrationTests(unittest.TestCase):
    def test_pose_angles_are_normalized_across_zero(self):
        self.assertAlmostEqual(normalize_angle_degrees(355.0), -5.0)
        self.assertAlmostEqual(normalize_angle_degrees(5.0), 5.0)
        self.assertAlmostEqual(normalize_angle_degrees(185.0), -175.0)
        self.assertAlmostEqual(unwrap_angle(179.0, -179.0), 181.0)
        self.assertAlmostEqual(unwrap_angle(-179.0, 179.0), -181.0)

    def test_screen_margin_keeps_cursor_out_of_failsafe_corner(self):
        calibration = Calibration(0.0, 0.0)
        position = calibration.map_to_screen(
            yaw=100.0,
            pitch=100.0,
            screen_width=1920,
            screen_height=1080,
            yaw_range=20.0,
            pitch_range=15.0,
            screen_margin=8,
        )
        self.assertEqual(position, (1911, 1071))

    def test_inverted_axes_map_top_left_direction_to_top_left_screen(self):
        calibration = Calibration(0.0, 0.0)
        position = calibration.map_to_screen(
            yaw=20.0,
            pitch=15.0,
            screen_width=1920,
            screen_height=1080,
            yaw_range=20.0,
            pitch_range=15.0,
            invert_yaw=True,
            invert_pitch=True,
            screen_margin=8,
        )
        self.assertEqual(position, (8, 8))

    def test_pose_estimator_rejects_single_frame_pose_jump(self):
        estimator = HeadPoseEstimator(
            smoothing_alpha=1.0,
            max_step_degrees=12.0,
            recovery_frames=3,
            median_window=1,
        )
        self.assertEqual(estimator._stabilize_angles(0.0, 0.0), (0.0, 0.0))
        self.assertEqual(estimator._stabilize_angles(30.0, 0.0), None)
        self.assertEqual(estimator.previous_angles, (0.0, 0.0))
        self.assertEqual(estimator._stabilize_angles(1.0, 0.0), (1.0, 0.0))
        self.assertFalse(estimator.recovery_history)

    def test_pose_estimator_recovers_after_sustained_pose_jump(self):
        estimator = HeadPoseEstimator(
            smoothing_alpha=1.0,
            max_step_degrees=12.0,
            recovery_frames=3,
            median_window=1,
        )
        self.assertEqual(estimator._stabilize_angles(0.0, 0.0), (0.0, 0.0))
        self.assertIsNone(estimator._stabilize_angles(30.0, 0.0))
        self.assertIsNone(estimator._stabilize_angles(31.0, 0.0))
        self.assertEqual(estimator._stabilize_angles(32.0, 0.0), (31.0, 0.0))
        self.assertEqual(estimator._stabilize_angles(33.0, 0.0), (33.0, 0.0))


if __name__ == "__main__":
    unittest.main()