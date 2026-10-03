"""Entry point for the webcam eye-controlled mouse."""

from __future__ import annotations

import math
import time

import cv2
import keyboard

import config
from blink_detector import BlinkDetector
from calibration import Calibration
from camera import Camera
from cloud_agent import CloudAgent
from face_tracker import FaceTracker
from head_pose import HeadPoseEstimator
from mouse_controller import MouseController
from ui import draw_debug, error_frame


def eye_aspect_ratio(face, indices: tuple[int, ...]) -> float:
    """Calculate EAR from six eyelid and eye-corner landmarks."""
    points = face.landmarks[list(indices), :2]
    horizontal = math.dist(points[0], points[3])
    if horizontal <= 1e-9:
        return 1.0
    vertical_one = math.dist(points[1], points[5])
    vertical_two = math.dist(points[2], points[4])
    return (vertical_one + vertical_two) / (2.0 * horizontal)


class KeyEdges:
    """Turn polled global keyboard states into one-shot key events."""

    def __init__(self) -> None:
        self.previous: dict[str, bool] = {}

    def pressed(self, key: str) -> bool:
        try:
            current = keyboard.is_pressed(key)
        except (OSError, ValueError):
            current = False
        was_pressed = self.previous.get(key, False)
        self.previous[key] = current
        return current and not was_pressed


def run() -> None:
    camera = None
    tracker = None
    cloud_agent = None
    try:
        camera = Camera(config.CAMERA_INDEX, config.CAMERA_WIDTH, config.CAMERA_HEIGHT, config.CAMERA_FPS)
        tracker = FaceTracker()
        pose_estimator = HeadPoseEstimator(
            smoothing_alpha=config.POSE_SMOOTHING_ALPHA,
            max_step_degrees=config.MAX_POSE_STEP_DEGREES,
            recovery_frames=config.POSE_RECOVERY_FRAMES,
            median_window=config.POSE_MEDIAN_WINDOW,
        )
        calibration = Calibration()
        mouse = MouseController(config.SMOOTHING_WINDOW, config.START_MOUSE_ENABLED)
        blink_detector = BlinkDetector(
            threshold=config.BLINK_THRESHOLD,
            threshold_ratio=config.BLINK_THRESHOLD_RATIO,
            min_threshold=config.MIN_BLINK_THRESHOLD,
            max_threshold=config.MAX_BLINK_THRESHOLD,
            min_calibration_ear=config.MIN_CALIBRATION_EAR,
            wink_calibration_seconds=config.WINK_CALIBRATION_SECONDS,
            closed_threshold_ratio=config.WINK_CLOSED_THRESHOLD_RATIO,
            blink_frames=config.BLINK_FRAMES,
            min_duration_ms=config.MIN_BLINK_MS,
            max_wink_ms=config.MAX_WINK_MS,
            simultaneous_window_ms=config.BOTH_EYE_WINDOW_MS,
        )
        cloud_agent = CloudAgent.from_saved_credentials()
        if cloud_agent is not None:
            cloud_agent.start()
        movement_settings = {
            "yaw_range_degrees": config.YAW_RANGE_DEGREES,
            "pitch_range_degrees": config.PITCH_RANGE_DEGREES,
        }
        keys = KeyEdges()
        last_frame_time = time.perf_counter()
        fps = 0.0
        status_message = "READY"

        while True:
            if cloud_agent is not None:
                remote_settings = cloud_agent.take_settings()
                if remote_settings is not None:
                    try:
                        movement_settings["yaw_range_degrees"] = max(
                            5.0,
                            min(60.0, float(remote_settings["yaw_range_degrees"])),
                        )
                        movement_settings["pitch_range_degrees"] = max(
                            5.0,
                            min(45.0, float(remote_settings["pitch_range_degrees"])),
                        )
                        mouse.set_smoothing_window(int(remote_settings["smoothing_window"]))
                        pose_estimator.smoothing_alpha = max(
                            0.05,
                            min(1.0, float(remote_settings["pose_smoothing_alpha"])),
                        )
                    except (KeyError, TypeError, ValueError):
                        status_message = "Invalid cloud settings ignored"

            ok, frame = camera.read()
            if not ok or frame is None:
                cv2.imshow(config.WINDOW_NAME, error_frame("Camera read failed. Press Q to exit."))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            now = time.perf_counter()
            elapsed = now - last_frame_time
            last_frame_time = now
            if elapsed > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / elapsed)

            face = tracker.process(frame, int(now * 1000))
            yaw = pitch = None
            left_ear = right_ear = None
            click_message = ""

            if face is None:
                blink_detector.reset()
                pose_estimator.reset()
                status_message = "Face not detected"
            else:
                height, width = frame.shape[:2]
                face_pixels = face.pixels(width, height)
                pose = pose_estimator.estimate(face_pixels, width, height)
                left_ear = eye_aspect_ratio(face, config.LEFT_EYE_LANDMARKS)
                right_ear = eye_aspect_ratio(face, config.RIGHT_EYE_LANDMARKS)
                if pose is not None:
                    yaw, pitch = pose
                    if keys.pressed("c"):
                        eyes_calibrated = blink_detector.calibrate_open_eyes(left_ear, right_ear)
                        if eyes_calibrated:
                            calibration.calibrate(yaw, pitch)
                            blink_detector.start_wink_calibration(now)
                        status_message = "Calibrated" if eyes_calibrated else "Calibration failed - open eyes"
                    target = calibration.map_to_screen(
                        yaw,
                        pitch,
                        mouse.screen_width,
                        mouse.screen_height,
                        movement_settings["yaw_range_degrees"],
                        movement_settings["pitch_range_degrees"],
                        config.HEAD_YAW_INVERT,
                        config.HEAD_PITCH_INVERT,
                        config.SCREEN_MARGIN,
                    )
                    mouse.move_to(target)
                else:
                    status_message = "Head pose unavailable"

                events = blink_detector.update(left_ear, right_ear, now)
                if events and mouse.enabled:
                    for event in events:
                        button = "left" if event.eye == "left" else "right"
                        mouse.click(button)
                        click_message = f"{event.eye.upper()} WINK -> {button.upper()} CLICK"
                elif events:
                    click_message = "WINK IGNORED - MOUSE DISABLED"

            if keys.pressed("f7"):
                enabled = mouse.toggle()
                status_message = "Mouse enabled" if enabled else "Mouse disabled"
            if keys.pressed("q"):
                break

            if cloud_agent is not None:
                cloud_agent.update_status({
                    "face_detected": face is not None,
                    "mouse_enabled": mouse.enabled,
                    "yaw": yaw,
                    "pitch": pitch,
                    "fps": fps,
                    "message": click_message or status_message,
                })

            info = {
                "Face": "DETECTED" if face is not None else "NOT DETECTED",
                "Mouse": "ENABLED" if mouse.enabled else "DISABLED",
                "Yaw": f"{yaw:.1f} deg" if yaw is not None else "--",
                "Pitch": f"{pitch:.1f} deg" if pitch is not None else "--",
                "Left EAR": f"{left_ear:.3f}" if left_ear is not None else "--",
                "Right EAR": f"{right_ear:.3f}" if right_ear is not None else "--",
                "Blink thresholds": f"{blink_detector.eye_threshold('left'):.3f} / {blink_detector.eye_threshold('right'):.3f}",
                "Eyes": blink_detector.last_status,
                "Calibration": "READY" if calibration.is_ready else "PRESS C",
                "Status": click_message or status_message,
                "FPS": f"{fps:.1f}",
            }
            cv2.imshow(config.WINDOW_NAME, draw_debug(frame, face, info, config.SHOW_MESH))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    except RuntimeError as error:
        cv2.imshow(config.WINDOW_NAME, error_frame(str(error)))
        cv2.waitKey(2500)
    finally:
        if cloud_agent is not None:
            cloud_agent.close()
        if tracker is not None:
            tracker.close()
        if camera is not None:
            camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    run()