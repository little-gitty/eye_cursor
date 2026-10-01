"""Independent eye blink and wink detection with simultaneous-blink filtering."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import monotonic


class EyePhase(Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass
class EyeState:
    phase: EyePhase = EyePhase.OPEN
    closed_since: float | None = None
    closed_frames: int = 0
    suppressed: bool = False


@dataclass(frozen=True)
class BlinkEvent:
    eye: str
    timestamp: float


class BlinkDetector:
    """Detect one event per short eye closure and ignore long or paired closures."""

    def __init__(
        self,
        threshold: float,
        blink_frames: int,
        min_duration_ms: int,
        max_wink_ms: int,
        simultaneous_window_ms: int,
        threshold_ratio: float = 0.55,
        min_threshold: float = 0.16,
        max_threshold: float = 0.34,
        min_calibration_ear: float = 0.30,
        wink_calibration_seconds: float = 5.0,
        closed_threshold_ratio: float = 0.50,
    ) -> None:
        self.threshold = threshold
        self.threshold_ratio = threshold_ratio
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.min_calibration_ear = min_calibration_ear
        self.wink_calibration_seconds = wink_calibration_seconds
        self.closed_threshold_ratio = closed_threshold_ratio
        self.open_ear: dict[str, float | None] = {
            "left": None,
            "right": None,
        }
        self.thresholds: dict[str, float] = {
            "left": float(threshold),
            "right": float(threshold),
        }
        self.blink_frames = blink_frames
        self.min_duration = min_duration_ms / 1000.0
        self.max_wink_duration = max_wink_ms / 1000.0
        self.simultaneous_window = simultaneous_window_ms / 1000.0
        self.states: dict[str, EyeState] = {
            "left": EyeState(),
            "right": EyeState(),
        }
        self.pending_events: list[BlinkEvent] = []
        self.last_status = "OPEN"
        self.wink_calibration_until: float | None = None
        self.wink_min_ear: dict[str, float | None] = {
            "left": None,
            "right": None,
        }

    def calibrate_open_eyes(self, left_ear: float, right_ear: float) -> bool:
        """Set independent blink thresholds from the current open-eye EAR values."""
        if left_ear < self.min_calibration_ear or right_ear < self.min_calibration_ear:
            return False
        self.open_ear = {
            "left": float(left_ear),
            "right": float(right_ear),
        }
        self.thresholds = {
            "left": max(
                self.min_threshold,
                min(self.max_threshold, left_ear * self.threshold_ratio),
            ),
            "right": max(
                self.min_threshold,
                min(self.max_threshold, right_ear * self.threshold_ratio),
            ),
        }
        self.reset()
        self.last_status = "EYE THRESHOLDS CALIBRATED"
        return True

    def start_wink_calibration(self, timestamp: float | None = None) -> None:
        """Start a no-click phase in which intentional winks set closed-eye EAR values."""
        now = monotonic() if timestamp is None else timestamp
        self.wink_calibration_until = now + self.wink_calibration_seconds
        self.wink_min_ear = {
            "left": None,
            "right": None,
        }
        self.reset()
        self.last_status = "WINK CALIBRATION: WINK LEFT AND RIGHT"

    def update(
        self,
        left_ear: float,
        right_ear: float,
        timestamp: float | None = None,
    ) -> list[BlinkEvent]:
        """Advance both eye state machines and return confirmed wink events."""
        now = monotonic() if timestamp is None else timestamp
        if self.wink_calibration_until is not None:
            return self._update_wink_calibration(left_ear, right_ear, now)
        closures: list[tuple[str, float, bool]] = []
        closures.extend(self._update_eye("left", left_ear, now))
        closures.extend(self._update_eye("right", right_ear, now))

        paired_closure = (
            len(closures) == 2
            and closures[0][0] != closures[1][0]
            and abs(closures[0][1] - closures[1][1]) <= self.simultaneous_window
        )
        if paired_closure:
            self.last_status = "NORMAL BLINK - IGNORED"
        else:
            for eye, event_time, valid in closures:
                if valid:
                    self.pending_events.append(BlinkEvent(eye, event_time))

        simultaneous_blink = self._suppress_simultaneous_events()
        confirmed = self._release_confirmed_events(now)
        self.last_status = "NORMAL BLINK - IGNORED" if simultaneous_blink else self._status_text()
        return confirmed

    def _update_wink_calibration(self, left_ear: float, right_ear: float, now: float) -> list[BlinkEvent]:
        for eye, ear in (("left", left_ear), ("right", right_ear)):
            current_min = self.wink_min_ear[eye]
            self.wink_min_ear[eye] = ear if current_min is None else min(current_min, ear)
        calibration_until = self.wink_calibration_until
        if calibration_until is not None and now < calibration_until:
            remaining = calibration_until - now
            self.last_status = f"WINK CALIBRATION {remaining:.1f}s"
            return []

        for eye in ("left", "right"):
            baseline = self.open_ear[eye]
            minimum = self.wink_min_ear[eye]
            if baseline is not None and minimum is not None and minimum < baseline:
                calibrated = minimum + ((baseline - minimum) * self.closed_threshold_ratio)
                self.thresholds[eye] = max(self.min_threshold, min(self.max_threshold, calibrated))
        self.wink_calibration_until = None
        self.reset()
        self.last_status = "WINK THRESHOLDS CALIBRATED"
        return []

    def reset(self) -> None:
        """Forget partial closures when landmarks are unavailable."""
        self.states = {
            "left": EyeState(),
            "right": EyeState(),
        }
        self.pending_events.clear()
        self.last_status = "OPEN"

    def _update_eye(self, eye: str, ear: float, now: float) -> list[tuple[str, float, bool]]:
        state = self.states[eye]
        is_closed = ear < self.thresholds[eye]
        closures: list[tuple[str, float, bool]] = []

        if is_closed and state.phase is EyePhase.OPEN:
            state.phase = EyePhase.CLOSED
            state.closed_since = now
            state.closed_frames = 1
            state.suppressed = False
        elif is_closed and state.phase is EyePhase.CLOSED:
            state.closed_frames += 1
        elif not is_closed and state.phase is EyePhase.CLOSED:
            started = state.closed_since if state.closed_since is not None else now
            duration = now - started
            valid = (
                state.closed_frames >= self.blink_frames
                and self.min_duration <= duration <= self.max_wink_duration
                and not state.suppressed
                and self._opposite_eye_is_open(eye)
            )
            closures.append((eye, now, valid))
            state.phase = EyePhase.OPEN
            state.closed_since = None
            state.closed_frames = 0
            state.suppressed = False
        return closures

    def _opposite_eye_is_open(self, eye: str) -> bool:
        opposite = "right" if eye == "left" else "left"
        return self.states[opposite].phase is EyePhase.OPEN

    def _suppress_simultaneous_events(self) -> bool:
        if len(self.pending_events) < 2:
            return False
        for index, first in enumerate(self.pending_events):
            for second in self.pending_events[index + 1 :]:
                if first.eye != second.eye and abs(first.timestamp - second.timestamp) <= self.simultaneous_window:
                    self.pending_events = [
                        event
                        for event in self.pending_events
                        if event is not first and event is not second
                    ]
                    return True
        return False

    def _release_confirmed_events(self, now: float) -> list[BlinkEvent]:
        confirmed: list[BlinkEvent] = []
        remaining: list[BlinkEvent] = []
        for event in self.pending_events:
            if now - event.timestamp > self.simultaneous_window:
                confirmed.append(event)
            else:
                remaining.append(event)
        self.pending_events = remaining
        return confirmed

    def _status_text(self) -> str:
        left = self.states["left"].phase.value
        right = self.states["right"].phase.value
        return f"LEFT: {left} | RIGHT: {right}"

    def eye_status(self, eye: str) -> str:
        return self.states[eye].phase.value

    def eye_threshold(self, eye: str) -> float:
        return self.thresholds[eye]

    def eye_baseline(self, eye: str) -> float | None:
        return self.open_ear[eye]
