const trimSlash = (value) => String(value || '').replace(/\/$/, '');

export const API_BASE = trimSlash(
  process.env.REACT_APP_API_BASE || 'http://127.0.0.1:8000'
);
export const WS_BASE = trimSlash(
  process.env.REACT_APP_WS_BASE || API_BASE.replace(/^http/, 'ws')
);

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  let data = null;
  try {
    data = await response.json();
  } catch (_) {
    data = null;
  }

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || `HTTP ${response.status}`);
  }
  return data;
}

export const api = {
  status: () => request('/api/status/'),
  devices: () => request('/api/camera/devices/'),
  disconnectCamera: () => request('/api/camera/disconnect/', { method: 'POST' }),
  setRoi: (rect) => request('/api/setup/roi/', { method: 'POST', body: JSON.stringify(rect) }),
  setGateBox: (rect) => request('/api/setup/gate-box/', { method: 'POST', body: JSON.stringify(rect) }),
  setLine: (line) => request('/api/setup/crossing-line/', { method: 'POST', body: JSON.stringify(line) }),
  calibrate: (rect) => request('/api/calibration/', { method: 'POST', body: JSON.stringify(rect) }),
  clearSetup: () => request('/api/setup/clear/', { method: 'POST' }),
  start: () => request('/api/counting/start/', { method: 'POST' }),
  stop: () => request('/api/counting/stop/', { method: 'POST' }),
  reset: () => request('/api/counting/reset/', { method: 'POST' }),
  patchConfig: (patch) => request('/api/config/', { method: 'PATCH', body: JSON.stringify(patch) }),
};

export function cameraSocket(serial) {
  const query = serial ? `?serial=${encodeURIComponent(serial)}` : '';
  return new WebSocket(`${WS_BASE}/ws/camera/${query}`);
}
