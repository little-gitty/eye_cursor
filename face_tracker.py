"""MediaPipe Tasks Face Landmarker adapter and landmark helpers."""

from __future__ import annotations

from dataclasses import dataclass

import mediapipe as mp
import numpy as np
from pathlib import Path

import config
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


@dataclass
class TrackedFace:
    landmarks: np.ndarray

    def pixels(self, width: int, height: int) -> np.ndarray:
        points = self.landmarks.copy()
        points[:, 0] *= width
        points[:, 1] *= height
        points[:, 2] *= max(width, height)
        return points


class FaceTracker:
    def __init__(self) -> None:
        model_path = Path(__file__).resolve().parent / config.FACE_LANDMARKER_MODEL_PATH
        if not model_path.is_file():
            raise RuntimeError(
                f"MediaPipe Tasks model not found: {model_path}. "
                "Download it with: "
                "Invoke-WebRequest https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task "
                "-OutFile models/face_landmarker.task"
            )
        base_options = python.BaseOptions(model_asset_path=str(model_path))
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.55,
            min_face_presence_confidence=0.55,
            min_tracking_confidence=0.55,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)

    def process(self, frame: np.ndarray, timestamp_ms: int) -> TrackedFace | None:
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame[:, :, ::-1])
        result = self.landmarker.detect_for_video(image, timestamp_ms)
        if not result.face_landmarks:
            return None
        landmarks = result.face_landmarks[0]
        values = np.array([(point.x, point.y, point.z) for point in landmarks], dtype=np.float64)
        return TrackedFace(values)

    def close(self) -> None:
        self.landmarker.close()
