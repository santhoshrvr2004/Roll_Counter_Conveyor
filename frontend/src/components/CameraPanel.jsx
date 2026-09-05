import React from 'react';
import {
  CameraIcon,
  ChevronDownIcon,
  DisconnectIcon,
  PlugIcon,
  RefreshIcon,
} from './Icons';

export default function CameraPanel({
  cameraConnected,
  cameraStatus,
  selectedDevice,
  selectedSerial,
  deviceOptions,
  onSerialChange,
  onRefreshDevices,
  onConnect,
  onDisconnect,
  busy,
}) {
  return (
    <section className="panel side-card camera-panel">
      <div className="panel-head">
        <span className="panel-title"><CameraIcon size={15} /> Camera</span>
        <span className={`led-label ${cameraConnected ? 'online' : ''}`}>
          <span className="led-dot" />
          {cameraConnected ? 'Online' : 'Offline'}
        </span>
      </div>

      <div className="panel-body camera-panel-body">
        <label className="field-caption" htmlFor="realsense-device">RealSense device</label>
        <div className="device-picker">
          <div className="select-wrap">
            <select
              id="realsense-device"
              value={selectedSerial || ''}
              disabled={cameraConnected}
              onChange={(event) => onSerialChange(event.target.value)}
            >
              <option value="">Auto-select first RealSense</option>
              {deviceOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <ChevronDownIcon size={13} />
          </div>
          <button
            type="button"
            className="icon-button"
            title="Refresh cameras"
            disabled={cameraConnected}
            onClick={onRefreshDevices}
          >
            <RefreshIcon size={14} />
          </button>
        </div>

        <button
          type="button"
          className={`button camera-connect-button ${cameraConnected ? 'button-danger-outline' : 'button-primary'}`}
          disabled={busy}
          onClick={cameraConnected ? onDisconnect : onConnect}
        >
          {cameraConnected ? <DisconnectIcon size={14} /> : <PlugIcon size={14} />}
          {cameraConnected ? 'Disconnect' : 'Connect RealSense'}
        </button>

        <div className="device-information">
          <span className={`led-dot ${cameraConnected ? 'online' : ''}`} />
          <strong>{cameraStatus || 'Disconnected'}</strong>
          <span className="device-name" title={selectedDevice}>{selectedDevice}</span>
        </div>
      </div>
    </section>
  );
}
