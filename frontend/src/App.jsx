import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api, cameraSocket } from './api';
import AppHeader from './components/AppHeader';
import StatCard from './components/StatCard';
import VideoStage from './components/VideoStage';
import CountPanel from './components/CountPanel';
import CameraPanel from './components/CameraPanel';
import SetupPanel from './components/SetupPanel';
import SettingsPanel from './components/SettingsPanel';
import { ArrowLeftIcon, TargetIcon, TracksIcon } from './components/Icons';
import './styles/app.css';
import './styles/components.css';
import './styles/responsive.css';

const DEFAULT_CONFIG = {
  area_tolerance: 40,
  threshold_fraction: 45,
  use_depth: true,
  depth_extra_mm: 100,
  max_merged_units: 3,
  match_distance: 90,
  max_missed: 12,
  min_hits: 3,
  hysteresis_px: 8,
  show_detections: true,
  show_ids: false,
  show_mask: false,
};

function toError(error) {
  return error instanceof Error ? error.message : String(error);
}

function normalizeStatus(data) {
  if (!data) return null;
  const next = { ...data };
  delete next.ok;
  delete next.type;
  return next;
}

function App() {
  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState(DEFAULT_CONFIG);
  const [devices, setDevices] = useState([]);
  const [selectedSerial, setSelectedSerial] = useState('');
  const [socket, setSocket] = useState(null);
  const [frameUrl, setFrameUrl] = useState('');
  const [drawMode, setDrawMode] = useState(null);
  const [messageText, setMessageText] = useState(
    'Connect the camera, then define ROI, count box, crossing line, and calibration piece.'
  );
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const configReady = useRef(false);
  const lastFrameUrl = useRef('');

  const applyStatus = useCallback((data) => {
    const next = normalizeStatus(data);
    if (!next) return;
    setStatus((previous) => ({ ...(previous || {}), ...next }));
    if (!configReady.current && next.config) {
      setConfig((current) => ({ ...current, ...next.config }));
      configReady.current = true;
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      applyStatus(await api.status());
    } catch (e) {
      setError(toError(e));
    }
  }, [applyStatus]);

  const refreshDevices = useCallback(async () => {
    setError('');
    try {
      const data = await api.devices();
      const nextDevices = data.devices || [];
      setDevices(nextDevices);
      setSelectedSerial((current) => current || nextDevices[0]?.serial || '');
    } catch (e) {
      setDevices([]);
      setError(toError(e));
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    refreshDevices();
    return () => {
      if (lastFrameUrl.current) URL.revokeObjectURL(lastFrameUrl.current);
    };
  }, [refreshStatus, refreshDevices]);

  const action = useCallback(async (fn, successMessage) => {
    setBusy(true);
    setError('');
    try {
      const data = await fn();
      applyStatus(data);
      if (data?.config) setConfig((current) => ({ ...current, ...data.config }));
      if (successMessage) setMessageText(successMessage);
      return data;
    } catch (e) {
      setError(toError(e));
      return null;
    } finally {
      setBusy(false);
    }
  }, [applyStatus]);

  const connect = useCallback(() => {
    if (socket && socket.readyState <= 1) return;
    setError('');
    setMessageText('Opening RealSense camera and WebSocket stream...');

    const ws = cameraSocket(selectedSerial || undefined);
    ws.binaryType = 'blob';

    ws.onopen = () => {
      setMessageText('Camera WebSocket connected. Waiting for live frames...');
    };

    ws.onmessage = (event) => {
      if (event.data instanceof Blob) {
        const url = URL.createObjectURL(event.data);
        if (lastFrameUrl.current) URL.revokeObjectURL(lastFrameUrl.current);
        lastFrameUrl.current = url;
        setFrameUrl(url);
        return;
      }

      try {
        const data = JSON.parse(event.data);
        if (data.type === 'error') {
          setError(data.message || data.error || 'Camera error');
        } else if (data.type === 'status') {
          applyStatus(data);
          if (data.camera_connected) setMessageText('RealSense camera connected and streaming.');
        }
      } catch (_) {
        // Ignore malformed non-binary WebSocket messages.
      }
    };

    ws.onerror = () => {
      setError('Camera WebSocket failed. Confirm the FastAPI backend is running on port 8000.');
    };

    ws.onclose = () => {
      setSocket((current) => (current === ws ? null : current));
      setMessageText('Camera stream closed.');
      refreshStatus();
    };

    setSocket(ws);
  }, [socket, selectedSerial, applyStatus, refreshStatus]);

  const disconnect = useCallback(async () => {
    if (socket) {
      try {
        socket.close(1000, 'User disconnected');
      } catch (_) {
        // Ignore socket close errors.
      }
    }
    setSocket(null);
    setFrameUrl('');
    if (lastFrameUrl.current) {
      URL.revokeObjectURL(lastFrameUrl.current);
      lastFrameUrl.current = '';
    }
    await action(api.disconnectCamera, 'Camera disconnected.');
  }, [socket, action]);

  const geometryDefined = useCallback(async (mode, geometry) => {
    setDrawMode(null);
    if (mode === 'roi') {
      await action(() => api.setRoi(geometry), 'ROI saved. Next, draw the count box.');
    } else if (mode === 'box') {
      await action(() => api.setGateBox(geometry), 'Count box saved. Next, draw the crossing line.');
    } else if (mode === 'line') {
      await action(() => api.setLine(geometry), 'Crossing line saved. Keep one isolated roll still and calibrate it.');
    } else if (mode === 'calibrate') {
      await action(() => api.calibrate(geometry), 'Calibration complete. Remove the calibration roll, then start counting.');
    }
  }, [action]);

  const beginDraw = (mode) => {
    if (!frameUrl) {
      setError('Connect the camera and wait for a live frame before drawing.');
      return;
    }
    setError('');
    setDrawMode(mode);
    const help = {
      roi: 'Drag around the complete conveyor processing region.',
      box: 'Drag a narrow count box around the intended line-crossing area.',
      line: 'Drag the crossing line across the conveyor inside the count box.',
      calibrate: 'Keep one isolated roll still and drag around it with a small belt border visible.',
    };
    setMessageText(help[mode]);
  };

  const patchConfig = async (patch) => {
    await action(async () => {
      const data = await api.patchConfig(patch);
      if (data?.config) setConfig((current) => ({ ...current, ...data.config }));
      return data;
    });
  };

  const setConfigField = (key, value) => {
    setConfig((current) => ({ ...current, [key]: value }));
  };

  const cameraConnected = Boolean(status?.camera_connected || frameUrl);
  const calibrated = Boolean(status?.calibrated);
  const setupComplete = Boolean(status?.roi && status?.gate_box && status?.crossing_line && calibrated);
  const calibration = status?.calibration;
  const selectedDevice = status?.camera_device?.name ||
    (selectedSerial ? `Serial ${selectedSerial}` : 'Auto-select first RealSense');

  const deviceOptions = devices.map((device) => ({
    value: device.serial,
    label: `${device.name}${device.serial ? ` · ${device.serial}` : ''}`,
  }));

  const setupItems = [
    { key: 'roi', label: 'Draw ROI', complete: Boolean(status?.roi) },
    { key: 'box', label: 'Count Box', complete: Boolean(status?.gate_box) },
    { key: 'line', label: 'Crossing Line', complete: Boolean(status?.crossing_line) },
    { key: 'calibrate', label: 'Calibrate', complete: calibrated },
  ];

  return (
    <div className="app-layout">
      <AppHeader
        cameraConnected={cameraConnected}
        cameraStatus={status?.camera_status}
        setupComplete={setupComplete}
        counting={Boolean(status?.counting)}
        onRefresh={refreshStatus}
      />

      {error ? (
        <div className="error-toast" role="alert">
          <span>{error}</span>
          <button type="button" className="error-toast-close" onClick={() => setError('')} aria-label="Dismiss error">
            ×
          </button>
        </div>
      ) : null}

      <main className="app-content">
        <section className="top-metrics">
          <StatCard
            label="B → A"
            value={status?.positive_to_negative ?? 0}
            icon={<ArrowLeftIcon size={18} />}
            tone="purple"
          />
          <StatCard
            label="Live detections"
            value={status?.diagnostics?.detections ?? 0}
            icon={<TargetIcon size={18} />}
            tone="orange"
          />
          <StatCard
            label="Active tracks"
            value={status?.diagnostics?.tracks ?? 0}
            icon={<TracksIcon size={18} />}
            tone="blue"
          />
        </section>

        <section className="dashboard-workspace">
          <div className="camera-column">
            <VideoStage
              frameUrl={frameUrl}
              frameSize={status?.frame_size}
              drawMode={drawMode}
              onGeometry={geometryDefined}
              connected={cameraConnected}
              onCancelDraw={() => setDrawMode(null)}
              messageText={messageText}
              setupComplete={setupComplete}
            />
          </div>

          <aside className="right-column">
            <CountPanel
              status={status}
              setupComplete={setupComplete}
              busy={busy}
              onToggleCounting={() => status?.counting
                ? action(api.stop, 'Counting paused.')
                : action(api.start, 'Counting enabled.')}
              onReset={() => action(api.reset, 'Count reset.')}
            />

            <div className="right-pair">
              <CameraPanel
                cameraConnected={cameraConnected}
                cameraStatus={status?.camera_status}
                selectedDevice={selectedDevice}
                selectedSerial={selectedSerial}
                deviceOptions={deviceOptions}
                onSerialChange={setSelectedSerial}
                onRefreshDevices={refreshDevices}
                onConnect={connect}
                onDisconnect={disconnect}
                busy={busy}
              />

              <SetupPanel
                setupItems={setupItems}
                drawMode={drawMode}
                setupComplete={setupComplete}
                onBeginDraw={beginDraw}
                onClear={() => action(api.clearSetup, 'Setup cleared.')}
                busy={busy}
              />
            </div>

            <SettingsPanel
              config={config}
              calibration={calibration}
              setConfigField={setConfigField}
              patchConfig={patchConfig}
            />
          </aside>
        </section>
      </main>
    </div>
  );
}

export default App;
