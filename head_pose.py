"""3D facial-landmark head-pose estimation."""

from __future__ import annotations

import cv2
import numpy as np
from collections import deque

from config import POSE_LANDMARKS


def normalize_angle_degrees(angle: float) -> float:
    """Convert an Euler angle to a continuous signed range of [-180, 180)."""
    return (angle + 180.0) % 360.0 - 180.0


def unwrap_angle(previous: float | None, current: float) -> float:
    """Choose the representation of current closest to the previous angle."""
    if previous is None:
        return current
    delta = normalize_angle_degrees(current - previous)
    return previous + delta


class HeadPoseEstimator:
    """Estimate yaw and pitch using a six-point generic 3D face model."""

    MODEL_POINTS = np.array([
        (0.0, 0.0, 0.0),
        (0.0, -330.0, -65.0),
        (-225.0, 170.0, -135.0),
        (225.0, 170.0, -135.0),
        (-150.0, -150.0, -125.0),
        (150.0, -150.0, -125.0),
    ], dtype=np.float64)

    def __init__(
        self,
        smoothing_alpha: float = 0.35,
        max_step_degrees: float = 12.0,
        recovery_frames: int = 5,
        median_window: int = 5,
    ) -> None:
        self.smoothing_alpha = max(0.0, min(1.0, smoothing_alpha))
        self.max_step_degrees = max(0.0, max_step_degrees)
        self.recovery_frames = max(1, recovery_frames)
        self.median_window = max(1, median_window | 1)
        self.previous_angles: tuple[float, float] | None = None
        self.previous_rotation_vector: np.ndarray | None = None
        self.previous_translation_vector: np.ndarray | None = None
        self.angle_history: deque[tuple[float, float]] = deque(maxlen=self.median_window)
        self.recovery_candidate: tuple[float, float] | None = None
        self.recovery_history: deque[tuple[float, float]] = deque(maxlen=self.recovery_frames)

    def estimate(self, face_pixels: np.ndarray, frame_width: int, frame_height: int) -> tuple[float, float] | None:
        image_points = face_pixels[list(POSE_LANDMARKS), :2].astype(np.float64)
        focal_length = float(frame_width)
        camera_matrix = np.array([
            [focal_length, 0.0, frame_width / 2.0],
            [0.0, focal_length, frame_height / 2.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)
        distortion = np.zeros((4, 1), dtype=np.float64)
        success, rotation_vector, translation_vector = cv2.solvePnP(
            self.MODEL_POINTS,
            image_points,
            camera_matrix,
            distortion,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            self.recovery_candidate = None
            self.recovery_history.clear()
            return None
        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        angles, *_ = cv2.RQDecomp3x3(rotation_matrix)
        pitch = normalize_angle_degrees(float(angles[0]))
        yaw = normalize_angle_degrees(float(angles[1]))
        if self.previous_angles is not None:
            yaw = unwrap_angle(self.previous_angles[0], yaw)
            pitch = unwrap_angle(self.previous_angles[1], pitch)

        stabilized = self._stabilize_angles(yaw, pitch)
        if stabilized is None:
            return self.previous_angles
        yaw, pitch = stabilized

        self.previous_rotation_vector = rotation_vector.copy()
        self.previous_translation_vector = translation_vector.copy()
        return yaw, pitch

    def _stabilize_angles(self, yaw: float, pitch: float) -> tuple[float, float] | None:
        if self.previous_angles is not None and self.max_step_degrees > 0.0:
            previous_yaw, previous_pitch = self.previous_angles
            if (
                abs(yaw - previous_yaw) > self.max_step_degrees
                or abs(pitch - previous_pitch) > self.max_step_degrees
            ):
                self._track_recovery_candidate(yaw, pitch)
                if len(self.recovery_history) < self.recovery_frames:
                    return None
                yaw = float(np.median([angle[0] for angle in self.recovery_history]))
                pitch = float(np.median([angle[1] for angle in self.recovery_history]))
                self.angle_history.clear()
                self.angle_history.extend(self.recovery_history)
                self.recovery_candidate = None
                self.recovery_history.clear()
                self.previous_angles = (yaw, pitch)
                return yaw, pitch
            else:
                self.recovery_candidate = None
                self.recovery_history.clear()

        self.angle_history.append((yaw, pitch))
        filtered_yaw = float(np.median([angle[0] for angle in self.angle_history]))
        filtered_pitch = float(np.median([angle[1] for angle in self.angle_history]))

        if self.previous_angles is not None:
            previous_yaw, previous_pitch = self.previous_angles
            yaw_delta = filtered_yaw - previous_yaw
            pitch_delta = filtered_pitch - previous_pitch
            alpha = self.smoothing_alpha
            yaw = previous_yaw + alpha * yaw_delta
            pitch = previous_pitch + alpha * pitch_delta
        else:
            yaw, pitch = filtered_yaw, filtered_pitch

        self.previous_angles = (yaw, pitch)
        return yaw, pitch

    def _track_recovery_candidate(self, yaw: float, pitch: float) -> None:
        candidate = (yaw, pitch)
        previous_candidate = self.recovery_candidate
        if previous_candidate is None or (
            abs(yaw - previous_candidate[0]) > self.max_step_degrees
            or abs(pitch - previous_candidate[1]) > self.max_step_degrees
        ):
            self.recovery_history.clear()
        self.recovery_history.append(candidate)
        self.recovery_candidate = candidate

    def reset(self) -> None:
        """Clear temporal pose state after a tracking interruption."""
        self.previous_angles = None
        self.previous_rotation_vector = None
        self.previous_translation_vector = None
        self.angle_history.clear()
        self.recovery_candidate = None
        self.recovery_history.clear()
