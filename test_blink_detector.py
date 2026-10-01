import unittest

from blink_detector import BlinkDetector


class BlinkDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = BlinkDetector(
            threshold=0.19,
            blink_frames=2,
            min_duration_ms=35,
            max_wink_ms=650,
            simultaneous_window_ms=150,
        )

    def feed(self, frames):
        events = []
        for timestamp, left, right in frames:
            events.extend(self.detector.update(left, right, timestamp))
        return events

    def test_short_left_wink_emits_once_after_confirmation_window(self):
        events = self.feed([
            (0.00, 0.30, 0.30),
            (0.05, 0.10, 0.30),
            (0.10, 0.10, 0.30),
            (0.20, 0.30, 0.30),
            (0.40, 0.30, 0.30),
        ])
        self.assertEqual([event.eye for event in events], ["left"])

    def test_long_closure_is_ignored(self):
        events = self.feed([
            (0.00, 0.30, 0.30),
            (0.05, 0.10, 0.30),
            (0.10, 0.10, 0.30),
            (0.80, 0.10, 0.30),
            (0.90, 0.30, 0.30),
            (1.20, 0.30, 0.30),
        ])
        self.assertEqual(events, [])

    def test_simultaneous_blink_is_ignored(self):
        events = self.feed([
            (0.00, 0.30, 0.30),
            (0.05, 0.10, 0.10),
            (0.10, 0.10, 0.10),
            (0.20, 0.30, 0.30),
            (0.40, 0.30, 0.30),
        ])
        self.assertEqual(events, [])

    def test_calibrated_thresholds_are_independent(self):
        self.detector.calibrate_open_eyes(0.48, 0.42)
        self.assertAlmostEqual(self.detector.eye_threshold("left"), 0.264)
        self.assertAlmostEqual(self.detector.eye_threshold("right"), 0.231)

    def test_calibrated_threshold_detects_closure_above_old_fixed_threshold(self):
        self.detector.calibrate_open_eyes(0.48, 0.42)
        events = self.feed([
            (0.00, 0.48, 0.42),
            (0.05, 0.24, 0.42),
            (0.10, 0.24, 0.42),
            (0.20, 0.48, 0.42),
            (0.40, 0.48, 0.42),
        ])
        self.assertEqual([event.eye for event in events], ["left"])

    def test_wink_calibration_learns_closed_eye_threshold_without_clicks(self):
        self.detector.calibrate_open_eyes(0.48, 0.42)
        self.detector.wink_calibration_seconds = 1.0
        self.detector.start_wink_calibration(0.0)
        self.assertEqual(self.detector.update(0.20, 0.42, 0.25), [])
        self.assertEqual(self.detector.update(0.48, 0.18, 0.75), [])
        self.assertEqual(self.detector.update(0.48, 0.42, 1.10), [])
        self.assertAlmostEqual(self.detector.eye_threshold("left"), 0.34)
        self.assertAlmostEqual(self.detector.eye_threshold("right"), 0.30)

    def test_wink_calibration_does_not_emit_events(self):
        self.detector.calibrate_open_eyes(0.48, 0.42)
        self.detector.wink_calibration_seconds = 0.5
        self.detector.start_wink_calibration(0.0)
        events = self.detector.update(0.10, 0.42, 0.20)
        events.extend(self.detector.update(0.48, 0.42, 0.70))
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
