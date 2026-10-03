import { useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import { Activity, ArrowLeftRight, Check, ChevronDown, CircleHelp, Clipboard, Eye, Gauge, Laptop, LogOut, MousePointer2, Plus, RefreshCw, Settings2, ShieldCheck, SlidersHorizontal, Unplug, Wifi, WifiOff } from 'lucide-react'
import type { Session } from '@supabase/supabase-js'
import { apiRequest } from './lib/api'
import { apiUrl, supabase } from './lib/supabase'
import type { Device, DeviceSettings, PairingCode } from './types'

const defaultSettings: DeviceSettings = {
  yaw_range_degrees: 20,
  pitch_range_degrees: 15,
  smoothing_window: 8,
  pose_smoothing_alpha: 0.35,
}

const SELF_DEVICE_STORAGE_KEY = 'eyemouse-self-device'

function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [authReady, setAuthReady] = useState(false)
  const [authMode, setAuthMode] = useState<'signin' | 'signup'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [authMessage, setAuthMessage] = useState('')
  const [authBusy, setAuthBusy] = useState(false)
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [settings, setSettings] = useState<DeviceSettings>(defaultSettings)
  const [pairingCode, setPairingCode] = useState<PairingCode | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const selectedDevice = devices.find((device) => device.id === selectedId) ?? devices[0] ?? null
  const connectedDevices = devices.filter(isOnline).length
  const token = session?.access_token
  const configured = Boolean(supabase)

  useEffect(() => {
    if (!supabase) {
      setAuthReady(true)
      return
    }
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setAuthReady(true)
    })
    const { data } = supabase.auth.onAuthStateChange((_event, value) => {
      setSession(value)
      setAuthReady(true)
    })
    return () => data.subscription.unsubscribe()
  }, [])

  async function registerSelfDevice() {
    if (!token) return null
    const saved = localStorage.getItem(SELF_DEVICE_STORAGE_KEY)
    if (saved) {
      try {
        const parsed = JSON.parse(saved) as { deviceId?: string; deviceToken?: string }
        if (parsed.deviceId) {
          return parsed.deviceId
        }
      } catch {
        localStorage.removeItem(SELF_DEVICE_STORAGE_KEY)
      }
    }

    const label = `This laptop (${navigator.userAgent ? navigator.userAgent.split(')')[0].split('(')[1] || 'Laptop' : 'Laptop'})`
    const created = await apiRequest<{ device_id: string; device_token: string; settings: DeviceSettings }>('/v1/devices/self', token, {
      method: 'POST',
      body: JSON.stringify({ label }),
    })
    localStorage.setItem(SELF_DEVICE_STORAGE_KEY, JSON.stringify({ deviceId: created.device_id, deviceToken: created.device_token }))
    return created.device_id
  }

  async function loadDevices(showError = true) {
    if (!token) return
    try {
      let result = await apiRequest<Device[]>('/v1/devices', token)

      if (result.length === 0) {
        const selfDeviceId = await registerSelfDevice()
        if (selfDeviceId) {
          result = await apiRequest<Device[]>('/v1/devices', token)
        }
      }

      setDevices(result)
      setSelectedId((current) => result.some((device) => device.id === current) ? current : result[0]?.id ?? '')
      setLastRefresh(new Date())
      if (showError) setError('')
    } catch (caught) {
      if (showError) setError(messageOf(caught))
    }
  }

  useEffect(() => {
    if (!token) {
      setDevices([])
      return
    }
    void loadDevices()
    const timer = window.setInterval(() => void loadDevices(false), 5000)
    return () => window.clearInterval(timer)
  }, [token])

  useEffect(() => {
    if (selectedDevice) setSettings(selectedDevice.settings)
  }, [selectedDevice?.id])

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!supabase) return
    setAuthBusy(true)
    setAuthMessage('')
    try {
      const result = authMode === 'signin'
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password })
      if (result.error) {
        const authError = result.error as typeof result.error & { code?: string; status?: number }
        const errorPrefix = [
          typeof authError.status === 'number' ? `HTTP ${authError.status}` : '',
          authError.code ?? '',
        ].filter(Boolean).join(' · ')
        const message = authError.code === 'over_email_send_rate_limit'
          ? 'Supabase’s built-in email sender is limited to 2 messages per hour. Stop retrying and wait for the limit to reset, or configure custom SMTP in Supabase Dashboard → Authentication → SMTP Settings.'
          : authError.message
        setAuthMessage(errorPrefix ? `${errorPrefix}: ${message}` : message)
      } else if (authMode === 'signup' && !result.data.session) {
        setAuthMessage('Account created. Check your inbox to confirm your email before signing in.')
      }
    } catch (caught) {
      setAuthMessage(messageOf(caught))
    } finally {
      setAuthBusy(false)
    }
  }

  async function createPairingCode() {
    if (!token) return
    setBusy(true)
    setError('')
    try {
      const result = await apiRequest<PairingCode>('/v1/pairing-codes', token, { method: 'POST' })
      setPairingCode(result)
      setNotice('Pairing code created. It expires in 10 minutes.')
    } catch (caught) {
      setError(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!token || !selectedDevice) return
    setBusy(true)
    setError('')
    try {
      await apiRequest(`/v1/devices/${selectedDevice.id}/settings`, token, {
        method: 'PATCH',
        body: JSON.stringify(settings),
      })
      setNotice('Settings saved. The local controller will apply them shortly.')
      await loadDevices(false)
    } catch (caught) {
      setError(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }

  async function removeDevice() {
    if (!token || !selectedDevice || !window.confirm(`Unpair ${selectedDevice.label}?`)) return
    setBusy(true)
    try {
      await apiRequest(`/v1/devices/${selectedDevice.id}`, token, { method: 'DELETE' })
      setNotice(`${selectedDevice.label} was unpaired.`)
      await loadDevices(false)
    } catch (caught) {
      setError(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }

  async function copyPairCommand() {
    if (!pairingCode) return
    const command = `python cloud_agent.py pair ${pairingCode.code} --api-url ${apiUrl}`
    await navigator.clipboard.writeText(command)
    setNotice('Pairing command copied.')
  }

  async function signOut() {
    await supabase?.auth.signOut()
  }

  if (!configured) return <SetupRequired />
  if (!authReady) return <div className="boot-screen"><div className="brand-mark"><Eye size={19} /></div><span>Connecting to your console…</span></div>
  if (!session) {
    return (
      <main className="auth-shell">
        <section className="auth-story">
          <div className="brand-lockup"><div className="brand-mark"><Eye size={19} /></div><span>eyemouse<span className="brand-period">.</span></span></div>
          <div className="story-copy">
            <span className="eyebrow">PERSONAL DEVICE CONSOLE</span>
            <h1>Your hands-free setup,<br /><em>in your hands.</em></h1>
            <p>Pair your Windows controller, tune movement, and check its connection. Camera processing stays on your computer.</p>
            <div className="privacy-note"><ShieldCheck size={17} /><span>Camera frames never leave your device.</span></div>
          </div>
          <div className="story-footer"><span>ACCESSIBILITY TOOLS, BUILT AROUND YOU</span><span>01 / PRIVATE BY DESIGN</span></div>
        </section>
        <section className="auth-panel">
          <div className="auth-card">
            <span className="eyebrow">{authMode === 'signin' ? 'WELCOME BACK' : 'CREATE YOUR ACCOUNT'}</span>
            <h2>{authMode === 'signin' ? 'Sign in' : 'Get started'}</h2>
            <p className="muted">Manage your paired computer and settings.</p>
            <form className="form-stack" onSubmit={submitAuth}>
              <label>Email address<input autoComplete="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required placeholder="you@example.com" /></label>
              <label>Password<input autoComplete={authMode === 'signin' ? 'current-password' : 'new-password'} type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} placeholder="At least 8 characters" /></label>
              {authMessage && <div className="inline-message">{authMessage}</div>}
              <button className="button button-primary button-wide" disabled={authBusy}>{authBusy ? 'Please wait…' : authMode === 'signin' ? 'Sign in' : 'Create account'}<span aria-hidden="true">→</span></button>
            </form>
            <p className="auth-switch">{authMode === 'signin' ? 'New to Eye Mouse?' : 'Already have an account?'} <button onClick={() => { setAuthMode(authMode === 'signin' ? 'signup' : 'signin'); setAuthMessage('') }}>{authMode === 'signin' ? 'Create an account' : 'Sign in'}</button></p>
            <div className="auth-privacy"><ShieldCheck size={15} /> Device video is processed locally, never uploaded.</div>
          </div>
        </section>
      </main>
    )
  }

  const status = selectedDevice?.status
  const online = selectedDevice ? isOnline(selectedDevice) : false
  const lastSeen = selectedDevice?.last_seen_at ? relativeTime(selectedDevice.last_seen_at) : 'Never connected'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup"><div className="brand-mark"><Eye size={18} /></div><span>eyemouse<span className="brand-period">.</span></span></div>
        <div className="workspace-label">WORKSPACE</div>
        <button className="workspace-picker"><span className="workspace-avatar">{(session.user.email ?? 'U')[0].toUpperCase()}</span><span className="workspace-email">{session.user.email}</span><ChevronDown size={15} /></button>
        <div className="nav-caption">CONTROL</div>
        <button className="nav-item active"><Activity size={17} /><span>Overview</span><span className="nav-pip" /></button>
        <button className="nav-item" onClick={() => document.getElementById('device-section')?.scrollIntoView({ behavior: 'smooth' })}><Laptop size={17} /><span>Devices</span><span className="nav-count">{devices.length}</span></button>
        <div className="sidebar-spacer" />
        <div className="sidebar-help"><div className="help-icon"><CircleHelp size={17} /></div><strong>Need a hand?</strong><p>Check the local agent and pairing guide in the README.</p><a href="https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python" target="_blank" rel="noreferrer">Tracking reference <span>↗</span></a></div>
        <button className="account-row" onClick={signOut}><span className="account-avatar">{(session.user.email ?? 'U')[0].toUpperCase()}</span><span className="account-name">{session.user.email}</span><LogOut size={16} /></button>
      </aside>

      <main className="main-area">
        <header className="topbar"><div className="breadcrumb">Console <span>/</span> <strong>Overview</strong></div><div className="topbar-right"><div className="secure-label"><ShieldCheck size={15} /> LOCAL PROCESSING</div><button className="icon-button" title="Refresh device status" onClick={() => void loadDevices()}><RefreshCw size={16} /></button></div></header>
        <div className="content-wrap">
          <section className="page-heading"><div><span className="eyebrow">YOUR CONTROL CENTER</span><h1>Good to see you<span className="heading-period">.</span></h1><p>Keep your computer connected and your controls feeling right.</p></div><button className="button button-primary" onClick={() => void createPairingCode()} disabled={busy}><Plus size={17} /> Register this laptop</button></section>
          {(error || notice) && <div className={`toast ${error ? 'toast-error' : 'toast-success'}`} role="status">{error || notice}<button onClick={() => { setError(''); setNotice('') }} aria-label="Dismiss">×</button></div>}

          <section className="overview-grid" aria-label="Device summary">
            <article className="metric-panel"><div className="metric-top"><span>COMPUTER STATUS</span><span className={`status-dot ${connectedDevices > 0 ? 'is-online' : ''}`} /></div><div className="metric-main"><strong>{connectedDevices.toString().padStart(2, '0')}</strong><span>of {devices.length.toString().padStart(2, '0')} online</span></div><div className="metric-foot"><Activity size={14} /> {connectedDevices ? 'Agent heartbeat received' : 'Waiting for a paired agent'}</div></article>
            <article className="metric-panel"><div className="metric-top"><span>POINTER CONTROL</span><MousePointer2 size={16} /></div><div className="metric-main metric-word"><strong>{status?.mouse_enabled && online ? 'Enabled' : 'Standby'}</strong></div><div className="metric-foot"><span className={`tiny-status ${status?.mouse_enabled && online ? 'tiny-green' : ''}`} /> Safety toggle remains local</div></article>
            <article className="metric-panel"><div className="metric-top"><span>FACE TRACKING</span><Eye size={16} /></div><div className="metric-main metric-word"><strong>{status?.face_detected && online ? 'Face found' : 'No active face'}</strong></div><div className="metric-foot"><span className={`tiny-status ${status?.face_detected && online ? 'tiny-green' : ''}`} /> {online ? `Updated ${lastSeen}` : 'Local camera only'}</div></article>
          </section>

          <section className="device-layout" id="device-section">
            <div className="section-column">
              <div className="section-title"><div><span className="eyebrow">CONNECTED HARDWARE</span><h2>Your computers</h2></div><span className="section-count">{devices.length} DEVICE{devices.length === 1 ? '' : 'S'}</span></div>
              {devices.length === 0 ? <div className="empty-state"><div className="empty-graphic"><Laptop size={27} /><span>+</span></div><h3>Nothing registered yet</h3><p>Your current laptop will be auto-registered when you first sign in, or you can register it manually here.</p><button className="button button-primary" onClick={() => void createPairingCode()} disabled={busy}><Plus size={16} /> Register this laptop</button></div> : <div className="device-list">{devices.map((device) => {
                const deviceOnline = isOnline(device)
                return <button className={`device-row ${selectedDevice?.id === device.id ? 'device-selected' : ''}`} key={device.id} onClick={() => setSelectedId(device.id)}><span className={`device-icon ${deviceOnline ? 'device-icon-live' : ''}`}><Laptop size={19} /></span><span className="device-copy"><strong>{device.label}</strong><span>{deviceOnline ? 'Connected now' : device.last_seen_at ? `Last seen ${relativeTime(device.last_seen_at)}` : 'Waiting for first connection'}</span></span><span className={`device-pill ${deviceOnline ? 'pill-online' : ''}`}><i />{deviceOnline ? 'ONLINE' : 'OFFLINE'}</span><ChevronDown className="device-chevron" size={16} /></button>
              })}</div>}
              {selectedDevice && <div className="telemetry-panel"><div className="telemetry-heading"><div><span className="eyebrow">LIVE TELEMETRY</span><h3>{selectedDevice.label}</h3></div><span className={`connection-tag ${online ? 'connection-live' : ''}`}>{online ? <><Wifi size={13} /> LIVE</> : <><WifiOff size={13} /> OFFLINE</>}</span></div><div className="telemetry-grid"><Telemetry label="YAW" value={online ? formatMetric(status?.yaw) : '—'} unit="deg" /><Telemetry label="PITCH" value={online ? formatMetric(status?.pitch) : '—'} unit="deg" /><Telemetry label="FRAME RATE" value={online ? formatMetric(status?.fps) : '—'} unit="fps" /></div><div className="telemetry-foot"><span>{online ? status?.message || 'Local controller reporting normally' : 'Waiting for local agent heartbeat'}</span><span>{lastRefresh ? `Synced ${lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : '—'}</span></div></div>}
            </div>

            <div className="settings-column">
              <div className="section-title settings-title"><div><span className="eyebrow">PERSONALIZE</span><h2>Movement settings</h2></div><Settings2 size={19} /></div>
              {selectedDevice ? <form className="settings-form" onSubmit={saveSettings}>
                <div className="settings-device"><span className="settings-device-icon"><SlidersHorizontal size={17} /></span><div><strong>{selectedDevice.label}</strong><span>{online ? 'Changes sync to local app' : 'Saved for next connection'}</span></div><span className={`save-indicator ${online ? 'save-online' : ''}`}><i /> {online ? 'SYNCED' : 'CLOUD'}</span></div>
                <SettingSlider title="Horizontal range" description="Head turn needed to reach screen edges" value={settings.yaw_range_degrees} min={8} max={45} step={1} unit="°" onChange={(value) => setSettings({ ...settings, yaw_range_degrees: value })} />
                <SettingSlider title="Vertical range" description="Head tilt needed to reach top and bottom" value={settings.pitch_range_degrees} min={6} max={35} step={1} unit="°" onChange={(value) => setSettings({ ...settings, pitch_range_degrees: value })} />
                <SettingSlider title="Smoothing" description="Higher values make cursor movement steadier" value={settings.smoothing_window} min={1} max={20} step={1} unit=" frames" onChange={(value) => setSettings({ ...settings, smoothing_window: value })} />
                <SettingSlider title="Pose response" description="How quickly tracking follows your movement" value={settings.pose_smoothing_alpha} min={0.1} max={0.9} step={0.05} unit="" display={`${Math.round(settings.pose_smoothing_alpha * 100)}%`} onChange={(value) => setSettings({ ...settings, pose_smoothing_alpha: value })} />
                <div className="settings-note"><ShieldCheck size={16} /><span>Mouse enable/disable and wink thresholds stay on the local computer for safety.</span></div>
                <button className="button button-dark button-wide" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save movement settings'}<span>→</span></button>
                {online && <button className="text-danger" type="button" onClick={() => void removeDevice()} disabled={busy}><Unplug size={14} /> Unpair this computer</button>}
              </form> : <div className="settings-empty"><Gauge size={23} /><p>Pair a computer to customize its movement settings.</p></div>}
            </div>
          </section>
          <footer className="page-footer"><span>EYEMOUSE CONSOLE <span className="footer-dot">/</span> PRIVATE BY DEFAULT</span><span>Camera frames stay on your computer</span></footer>
        </div>
      </main>

      {pairingCode && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPairingCode(null) }}><section className="pair-modal" role="dialog" aria-modal="true" aria-labelledby="pair-title"><button className="modal-close" onClick={() => setPairingCode(null)} aria-label="Close">×</button><div className="pair-badge"><ArrowLeftRight size={19} /></div><span className="eyebrow">SECURE DEVICE LINK</span><h2 id="pair-title">Pair your computer</h2><p className="muted">This one-time code expires at {new Date(pairingCode.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}.</p><div className="pair-code">{pairingCode.code.split('').map((character, index) => <span key={`${character}-${index}`}>{character}</span>)}</div><div className="pair-command-label">RUN THIS IN YOUR PROJECT FOLDER</div><button className="copy-command" onClick={() => void copyPairCommand()}><code>python cloud_agent.py pair {pairingCode.code} --api-url {apiUrl}</code><Clipboard size={16} /></button><div className="pair-privacy"><ShieldCheck size={16} /><span>Pairing sends device status and settings only. Webcam video is never sent.</span></div><button className="button button-dark button-wide" onClick={() => { setPairingCode(null); void loadDevices() }}><Check size={16} /> Done</button></section></div>}
    </div>
  )
}

function SetupRequired() {
  return <main className="setup-screen"><div className="brand-mark"><Eye size={19} /></div><span className="eyebrow">DASHBOARD SETUP</span><h1>Connect your cloud project.</h1><p>Add Supabase and API settings to <code>web/.env.local</code>, then restart the Vite server.</p><pre>VITE_SUPABASE_URL=…<br />VITE_SUPABASE_ANON_KEY=…<br />VITE_API_URL=http://localhost:8000</pre></main>
}

function Telemetry({ label, value, unit }: { label: string; value: string; unit: string }) {
  return <div className="telemetry-stat"><span>{label}</span><strong>{value}<small>{unit}</small></strong></div>
}

function SettingSlider({ title, description, value, min, max, step, unit, display, onChange }: { title: string; description: string; value: number; min: number; max: number; step: number; unit: string; display?: string; onChange: (value: number) => void }) {
  const fill = `${((value - min) / (max - min)) * 100}%`
  return <label className="slider-setting"><span className="slider-heading"><span><strong>{title}</strong><small>{description}</small></span><output>{display ?? `${value}${unit}`}</output></span><input type="range" min={min} max={max} step={step} value={value} style={{ '--range-fill': fill } as CSSProperties} onChange={(event) => onChange(Number(event.target.value))} /></label>
}

function isOnline(device: Device): boolean {
  return Boolean(device.last_seen_at && Date.now() - new Date(device.last_seen_at).getTime() < 25_000)
}

function relativeTime(value: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000))
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  return `${Math.floor(seconds / 60)}m ago`
}

function formatMetric(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(1) : '—'
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

export default App
