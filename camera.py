"""Webcam capture lifecycle."""

from __future__ import annotations

import cv2


class Camera:
    def __init__(self, index: int, width: int, height: int, fps: int) -> None:
        self.capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not self.capture.isOpened():
            self.capture.release()
            self.capture = cv2.VideoCapture(index)
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open webcam {index}")
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.capture.set(cv2.CAP_PROP_FPS, fps)

    def read(self):
        if self.capture is None or not self.capture.isOpened():
            return False, None
        return self.capture.read()

    def release(self) -> None:
        if self.capture is not None:
            self.capture.release()
