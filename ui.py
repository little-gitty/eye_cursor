"""OpenCV debug rendering."""

from __future__ import annotations

import cv2
import numpy as np

from config import (
    DEBUG_ACCENT_COLOR,
    DEBUG_ERROR_COLOR,
    DEBUG_TEXT_COLOR,
    DEBUG_WARNING_COLOR,
    LEFT_EYE_LANDMARKS,
    RIGHT_EYE_LANDMARKS,
)


def draw_debug(
    frame: np.ndarray,
    face,
    info: dict[str, str],
    show_mesh: bool = True,
) -> np.ndarray:
    output = frame.copy()
    if face is not None and show_mesh:
        height, width = output.shape[:2]
        for index, point in enumerate(face.landmarks):
            color = DEBUG_ACCENT_COLOR if index in LEFT_EYE_LANDMARKS + RIGHT_EYE_LANDMARKS else (110, 150, 190)
            x, y = int(point[0] * width), int(point[1] * height)
            cv2.circle(output, (x, y), 1 if index not in LEFT_EYE_LANDMARKS + RIGHT_EYE_LANDMARKS else 2, color, -1)

    panel_height = 255
    cv2.rectangle(output, (0, 0), (410, panel_height), (25, 30, 35), -1)
    cv2.putText(output, "Eye Mouse Controller", (15, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.7, DEBUG_TEXT_COLOR, 2)
    y = 55
    for label, value in info.items():
        color = DEBUG_TEXT_COLOR
        if "DISABLED" in value or "NOT" in value or "ERROR" in value:
            color = DEBUG_WARNING_COLOR
        if "BLINK" in value or "CLICK" in value:
            color = DEBUG_ACCENT_COLOR
        cv2.putText(output, f"{label}: {value}", (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1)
        y += 22
    return output


def error_frame(message: str, width: int = 800, height: int = 450) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(frame, message, (30, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, DEBUG_ERROR_COLOR, 2)
    return frame
