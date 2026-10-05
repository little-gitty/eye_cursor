export type DeviceSettings = {
  yaw_range_degrees: number
  pitch_range_degrees: number
  smoothing_window: number
  pose_smoothing_alpha: number
}

export type DeviceStatus = {
  connected?: boolean
  face_detected?: boolean
  mouse_enabled?: boolean
  yaw?: number | null
  pitch?: number | null
  fps?: number | null
  message?: string
}

export type Device = {
  id: string
  label: string
  settings: DeviceSettings
  status: DeviceStatus
  created_at: string
  last_seen_at: string | null
}

export type PairingCode = {
  code: string
  expires_at: string
}
