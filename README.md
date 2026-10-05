# Eye-Controlled Mouse

A Windows accessibility-oriented mouse controller using a normal webcam, OpenCV, MediaPipe Tasks Face Landmarker, and PyAutoGUI.

## Repository layout

```text
backend/       FastAPI cloud/local API and database schema
docs/          React + Vite dashboard
models/        Local MediaPipe face-landmarker model
*.py           Local Windows camera, tracking, calibration, and mouse-control app
render.yaml    Render API deployment blueprint
requirements.txt
               Dependencies for the local Windows camera app
```

The dashboard and API can be deployed independently from the local Windows camera app. The local app owns webcam access, face tracking, and OS mouse control; the API stores accounts, device settings, and status.

## Features

- 3D `solvePnP` head-pose estimation for cursor direction
- Neutral-position calibration held in memory for the current run
- Smoothed, clamped cursor movement
- Independent left/right eye EAR measurements
- One left click per short left wink
- One right click per short right wink
- Normal simultaneous blinks ignored
- Long eye closures ignored
- Mouse control starts disabled as a safety measure
- Debug window with landmarks, EAR, pose, state, calibration, and FPS

## Installation

Use Python 3.12 or newer on Windows. The project uses the current MediaPipe Tasks Face Landmarker API.

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
```

If `python` selects a different interpreter, use the Python 3.12 launcher explicitly:

```powershell
py -3.12 -m venv venv
venv\Scripts\activate
py -3.12 -m pip install -r requirements.txt
```

The Face Landmarker task requires its model file. Download it from the project folder with:

```powershell
New-Item -ItemType Directory -Force models
Invoke-WebRequest https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task -OutFile models/face_landmarker.task
```

The model is stored in `models/face_landmarker.task` and is resolved relative to the project, so the application can be started from any working directory.

## Running

Use the launcher to choose a built-in or external camera and start eye cursor locally:

```powershell
python launcher.py
```

The launcher starts the controller without cloud registration or cloud requests. You can also use the default camera directly:

```powershell
python main.py --local-only
```

The application opens the selected webcam and an OpenCV debug window. It does not write calibration to disk; each execution starts uncalibrated. Cloud pairing is optional and is only used when explicitly configured and started outside local-only mode.

## Controls

- `C`: calibrate while looking straight at the camera
- `F7`: toggle mouse movement and clicking
- `Q`: quit

Mouse control starts **disabled**. Enable it with `F7` after calibration.

## Mouse controls

- Move your head left/right/up/down to move the cursor toward the corresponding screen edge.
- A short left-eye wink produces one left click.
- A short right-eye wink produces one right click.
- A normal two-eye blink produces no click.
- Holding either eye closed beyond the configured duration produces no click.

The click is intentionally delayed by the simultaneous-blink tolerance window so the detector can distinguish a wink from an ordinary blink.

## Calibration

1. Sit at a comfortable distance from the webcam.
2. Position the webcam so your full face is visible.
3. Look straight at the center of the screen.
4. Keep both eyes open and press `C`. This calibrates the neutral head pose and each eye's open EAR baseline.
5. For the next five seconds, wink once with the left eye and once with the right eye when the debug status says `WINK CALIBRATION`.
6. Press `F7` to enable mouse control. It starts disabled for safety.
7. Move your head naturally and adjust settings in `config.py` if needed.

The wink-learning phase does not click. It records the lowest EAR observed for each eye and uses those measurements to set independent wink thresholds. If the cursor becomes disabled after reaching the screen corner, press `F7` to re-enable it; the controller keeps an 8-pixel margin from the Windows PyAutoGUI emergency corner.

If left/right or up/down feels reversed, change `HEAD_YAW_INVERT` or `HEAD_PITCH_INVERT` in `config.py`.

## Configuration

The main tuning values are centralized in `config.py`:

- `SMOOTHING_WINDOW`: cursor stability versus responsiveness
- `POSE_SMOOTHING_ALPHA`: per-frame head-pose responsiveness; lower values reduce jitter
- `MAX_POSE_STEP_DEGREES`: maximum accepted one-frame pose change; larger jumps are treated as bad landmark/PnP results
- `POSE_RECOVERY_FRAMES`: consecutive rejected pose frames before accepting a sustained new pose and recovering from a solver branch
- `YAW_RANGE_DEGREES` and `PITCH_RANGE_DEGREES`: head movement needed to reach screen edges
- `BLINK_THRESHOLD`: EAR value below which an eye is considered closed
- `BLINK_THRESHOLD_RATIO`: fraction of each calibrated open-eye EAR used as the closed-eye threshold
- `MIN_BLINK_THRESHOLD` and `MAX_BLINK_THRESHOLD`: safety bounds for calibrated thresholds
- `WINK_CALIBRATION_SECONDS`: duration of the post-`C` wink-learning phase
- `SCREEN_MARGIN`: distance kept from the PyAutoGUI failsafe corner and screen edges
- `BLINK_FRAMES`: consecutive closed frames required
- `MIN_BLINK_MS` and `MAX_WINK_MS`: accepted short-closure duration
- `BOTH_EYE_WINDOW_MS`: timing tolerance used to reject normal blinks

## Architecture

```text
WEBCAM
   |
   v
MediaPipe Tasks Face Landmarker
   |
   +------------------+
   |                  |
   v                  v
HEAD POSE          EYE STATE
   |                  |
   v             +----+----+
CURSOR MAP       |         |
   |             v         v
   v         LEFT WINK  RIGHT WINK
MOUSE            |         |
   |             v         v
   +-------- LEFT CLICK  RIGHT CLICK
```

The code is split by responsibility: camera capture, face tracking, pose estimation, calibration, blink state handling, mouse output, UI rendering, and application orchestration.

## Testing

The blink state machine has hardware-independent tests:

```powershell
py -3.12 -m unittest -v test_blink_detector.py
```

A physical webcam is required to verify live landmark tracking and cursor behavior.

## Online Dashboard (Optional)

The dashboard manages accounts, paired Windows devices, connection status, and movement settings. Webcam capture, face tracking, and OS mouse control continue to run locally; video frames are never uploaded.

### Dashboard features

- Create an account or sign in with email and password through Supabase Authentication.
- View paired computers, their online/offline state, last-seen time, and current face-tracking and pointer-control status.
- Inspect live yaw, pitch, and frame-rate telemetry. Device status refreshes automatically every five seconds, and can also be refreshed manually.
- Select a computer and adjust its horizontal range (8–45°), vertical range (6–35°), smoothing window (1–20 frames), and pose response (10–90%). Save changes to sync them to the local controller; changes are kept in the cloud for the next connection when the device is offline.
- Keep mouse enable/disable and wink thresholds on the local computer as safety controls. Camera frames remain local and are never uploaded.

### Services

- `docs/`: React + Vite dashboard, deployed to GitHub Pages
- `backend/`: FastAPI cloud API, deployable to Render
- Root-level Python modules: local Windows camera and eye-tracking application
- Supabase: account authentication and PostgreSQL storage
- `cloud_agent.py`: optional local pairing and background settings/status client

### Supabase setup

1. Create a Supabase project.
2. In the SQL Editor, run `backend/schema.sql`.
3. Copy the project URL, anon key, and service-role key from Project Settings. Keep the service-role key private; it belongs only in the API host's environment.

### Run the API locally

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt -r ..\requirements.txt
Copy-Item .env.example .env
```

Install both requirement files for local development: the backend environment also launches the local camera picker, which needs the root-level OpenCV and MediaPipe dependencies. Fill `backend/.env` with the Supabase values and set `CORS_ORIGINS=http://localhost:5173`, then start the API:

```powershell
uvicorn main:app --reload --port 8000
```

### Run the dashboard locally

In another terminal:

```powershell
cd docs
npm install
Copy-Item .env.example .env.local
```

Set the Supabase URL and anon key in `docs/.env.local`, keep `VITE_API_URL=http://localhost:8000`, then run:

```powershell
npm run dev
```

Open the URL Vite prints, create an account, and sign in. Supabase email confirmation may need to be enabled or configured for the project.

### Open the camera from the dashboard

With the dashboard and local API running on the same Windows computer, sign in and choose **Open camera**. The local camera picker and Eye Cursor tracking window open without creating additional command-line windows. Choose a connected camera, then select **Start Eye Cursor**. The terminal already running the local API stays open; it hosts the API and is separate from the camera windows. Camera frames are processed locally and are never uploaded.

Cloud pairing is optional. To pair a Windows computer for dashboard status and settings, run `python cloud_agent.py pair <code> --api-url <api-url>` with a valid one-time code and the cloud API URL from the project folder. The agent uploads status and fetches settings, not webcam frames.

The device token is saved under `%APPDATA%\EyeMouse\device.json`. Unpairing deletes the cloud device record, which revokes its token. Local control remains usable if the cloud API is unavailable.

### Deploy

The dashboard is built and deployed to GitHub Pages by `.github/workflows/deploy-pages.yml` whenever a commit is pushed to `main`, or manually with **Run workflow** in the repository's Actions tab. The API runs separately on Render, and Supabase provides authentication and PostgreSQL storage. The Pages site URL for this repository is `https://little-gitty.github.io/eye_cursor/`.

1. In Supabase, run `backend/schema.sql`. Under Authentication → URL Configuration, set the Site URL to `https://little-gitty.github.io/eye_cursor/` and add `https://little-gitty.github.io/eye_cursor/**` to the allowed redirect URLs.
2. In Render, create a Blueprint instance from the repository's root `render.yaml`. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`. Set `CORS_ORIGINS` to `https://little-gitty.github.io` (the origin only; do not include `/eye_cursor/`).
3. In GitHub, open the repository's **Settings → Secrets and variables → Actions → Variables** and add `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, and `VITE_API_URL`, with the deployed Render API base URL as `VITE_API_URL`. These frontend values are public and are embedded in the site at build time. Do not put the Supabase service-role key in GitHub Actions variables or any `VITE_*` setting.
4. In **Settings → Pages**, set the build and deployment source to **GitHub Actions**. Push to `main` or run the workflow manually. Verify the Render `/health` URL returns `{"status":"ok","service":"eye-mouse-cloud"}`, then open the Pages URL and sign in.

Never expose `SUPABASE_SERVICE_ROLE_KEY` in GitHub Actions variables or any `VITE_*` variable. The service role bypasses database row-level security and is only used by the API server.

**Camera-launch limitation for hosted dashboards:** GitHub Pages is a static host and Render cannot access a visitor's webcam or start a Windows GUI on the visitor's computer. The hosted API explicitly rejects `/v1/camera/open`; camera launch must be done by software running locally on the Windows computer, for example `.\.venv\Scripts\python.exe launcher.py` from the project folder. Webcam frames remain local and must never be sent to the cloud API.

### API tests

```powershell
cd backend
python -m unittest -v test_api.py
```
