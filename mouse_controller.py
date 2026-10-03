"""Safety-gated, smoothed Windows mouse output."""

from __future__ import annotations

from collections import deque

import pyautogui


class MouseController:
    def __init__(self, smoothing_window: int, enabled: bool) -> None:
        self.enabled = enabled
        self.screen_width, self.screen_height = pyautogui.size()
        self.positions = deque(maxlen=max(1, smoothing_window))
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.0

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        self.positions.clear()
        return self.enabled

    def set_smoothing_window(self, window: int) -> None:
        """Update the cursor averaging window from validated remote settings."""
        self.positions = deque(self.positions, maxlen=max(1, min(24, int(window))))

    def move_to(self, position: tuple[int, int] | None) -> None:
        if not self.enabled or position is None:
            return
        x = max(0, min(self.screen_width - 1, position[0]))
        y = max(0, min(self.screen_height - 1, position[1]))
        self.positions.append((x, y))
        average_x = round(sum(item[0] for item in self.positions) / len(self.positions))
        average_y = round(sum(item[1] for item in self.positions) / len(self.positions))
        try:
            pyautogui.moveTo(average_x, average_y, _pause=False)
        except pyautogui.FailSafeException:
            self.enabled = False

    def click(self, button: str) -> None:
        if not self.enabled:
            return
        try:
            pyautogui.click(button=button)
        except pyautogui.FailSafeException:
            self.enabled = False
