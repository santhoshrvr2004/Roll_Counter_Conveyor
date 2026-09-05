import React from 'react';
import {
  CheckIcon,
  GaugeIcon,
  PauseIcon,
  PlayIcon,
  RefreshIcon,
  SettingsIcon,
} from './Icons';



export default function AppHeader({
  cameraConnected,
  cameraStatus,
  setupComplete,
  counting,
  onRefresh,
}) {
  return (
    <header className="app-header">
      <div className="brand-block">
        <div className="brand-icon">
  <img src="/logo.png" alt="RealSense Conveyor Counter Logo" />
</div>
        <div className="brand-copy">
          <h1 className="brand-title">RealSense Conveyor Counter</h1>
          {/* <span className="brand-subtitle">
            FastAPI · WebSocket · calibrated area + depth counting
          </span> */}
        </div>
      </div>

      <div className="header-center-status">
        <span className={`status-chip ${setupComplete ? 'chip-success' : 'chip-info'}`}>
          {setupComplete ? <CheckIcon size={13} /> : <SettingsIcon size={13} />}
          {setupComplete ? 'Setup ready' : 'Setup required'}
        </span>
        <span className={`status-chip ${counting ? 'chip-success' : 'chip-neutral'}`}>
          {counting ? <PlayIcon size={13} /> : <PauseIcon size={13} />}
          {counting ? 'Counting active' : 'Counting stopped'}
        </span>
      </div>

      <div className="header-actions">
        <button
          type="button"
          className="icon-button header-refresh"
          title="Refresh backend status"
          onClick={onRefresh}
        >
          <RefreshIcon size={15} />
        </button>
        <div className={`header-camera-state ${cameraConnected ? 'online' : ''}`}>
          <span className="header-status-dot" />
          <div>
            <strong>{cameraConnected ? 'Camera online' : 'Camera offline'}</strong>
            <small>{cameraStatus || 'Disconnected'}</small>
          </div>
        </div>
      </div>
    </header>
  );
}
