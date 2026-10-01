"""In-memory neutral head-pose calibration and screen mapping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Calibration:
    neutral_yaw: float | None = None
    neutral_pitch: float | None = None

    @property
    def is_ready(self) -> bool:
        return self.neutral_yaw is not None and self.neutral_pitch is not None

    def calibrate(self, yaw: float, pitch: float) -> None:
        self.neutral_yaw = yaw
        self.neutral_pitch = pitch

    def map_to_screen(
        self,
        yaw: float,
        pitch: float,
        screen_width: int,
        screen_height: int,
        yaw_range: float,
        pitch_range: float,
        invert_yaw: bool = False,
        invert_pitch: bool = False,
        screen_margin: int = 0,
    ) -> tuple[int, int] | None:
        if not self.is_ready or yaw_range <= 0 or pitch_range <= 0:
            return None
        yaw_delta = yaw - self.neutral_yaw
        pitch_delta = pitch - self.neutral_pitch
        if invert_yaw:
            yaw_delta *= -1
        if invert_pitch:
            pitch_delta *= -1
        horizontal = max(-1.0, min(1.0, yaw_delta / yaw_range))
        vertical = max(-1.0, min(1.0, pitch_delta / pitch_range))
        margin_x = min(max(0, screen_margin), max(0, (screen_width - 1) // 2))
        margin_y = min(max(0, screen_margin), max(0, (screen_height - 1) // 2))
        usable_width = screen_width - 1 - (2 * margin_x)
        usable_height = screen_height - 1 - (2 * margin_y)
        x = margin_x + round((horizontal + 1.0) * 0.5 * usable_width)
        y = margin_y + round((vertical + 1.0) * 0.5 * usable_height)
        return x, y
