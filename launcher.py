"""Small local launcher for choosing a camera and starting Eye Mouse."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from camera import available_camera_indices


PROJECT_ROOT = Path(__file__).resolve().parent


class EyeMouseLauncher:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.process: subprocess.Popen[bytes] | None = None
        self.camera_indices: list[int] = []
        root.title("Eye Mouse")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.close)

        frame = ttk.Frame(root, padding=20)
        frame.grid(sticky="nsew")
        ttk.Label(frame, text="Eye Mouse", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Choose a camera to start local eye cursor control.").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 16)
        )
        ttk.Label(frame, text="Camera").grid(row=2, column=0, sticky="w", padx=(0, 12))
        self.camera_choice = tk.StringVar()
        self.camera_list = ttk.Combobox(frame, textvariable=self.camera_choice, state="readonly", width=24)
        self.camera_list.grid(row=2, column=1, sticky="ew")
        self.refresh_button = ttk.Button(frame, text="Refresh", command=self.refresh_cameras)
        self.refresh_button.grid(row=3, column=0, sticky="w", pady=(12, 0))
        self.start_button = ttk.Button(frame, text="Start Eye Cursor", command=self.start)
        self.start_button.grid(row=3, column=1, sticky="e", pady=(12, 0))
        self.status = tk.StringVar(value="Scanning cameras…")
        ttk.Label(frame, textvariable=self.status).grid(row=4, column=0, columnspan=2, sticky="w", pady=(14, 0))
        ttk.Label(frame, text="Camera processing stays on this computer; cloud pairing is optional.").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        self.refresh_cameras()
        self.root.after(500, self.check_process)

    def refresh_cameras(self) -> None:
        self.status.set("Scanning cameras…")
        self.refresh_button.configure(state="disabled")
        self.root.update_idletasks()
        try:
            self.camera_indices = available_camera_indices()
        finally:
            self.refresh_button.configure(state="normal")
        self.camera_list["values"] = [f"Camera {index}" for index in self.camera_indices]
        if self.camera_indices:
            self.camera_list.current(0)
            self.start_button.configure(state="normal")
            self.status.set(f"Found {len(self.camera_indices)} camera(s).")
        else:
            self.camera_choice.set("")
            self.start_button.configure(state="disabled")
            self.status.set("No camera found. Connect one and refresh.")

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.status.set("Eye Cursor is already running.")
            return
        selection = self.camera_list.current()
        if selection < 0:
            messagebox.showerror("No camera selected", "Refresh the camera list and choose a camera.")
            return
        camera_index = self.camera_indices[selection]
        try:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "main.py"),
                    "--camera-index",
                    str(camera_index),
                    "--local-only",
                ],
                cwd=PROJECT_ROOT,
            )
        except OSError as error:
            messagebox.showerror("Could not start Eye Cursor", str(error))
            return
        self.status.set(f"Starting Eye Cursor with Camera {camera_index}…")
        self.start_button.configure(state="disabled")

    def check_process(self) -> None:
        if self.process is not None and self.process.poll() is not None:
            self.process = None
            self.start_button.configure(state="normal" if self.camera_indices else "disabled")
            self.status.set("Eye Cursor stopped.")
        self.root.after(500, self.check_process)

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    EyeMouseLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()