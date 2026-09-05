import React, { useState } from 'react';
import { EyeIcon, FlaskIcon, InfoIcon, SettingsIcon, TracksIcon } from './Icons';

function Field({ label, hint, children }) {
  return (
    <div className="setting-field">
      <div className="setting-field-label">
        <span>{label}</span>
        {hint ? (
      <span className="hint-icon" title={hint}><InfoIcon size={12} /></span>
        ) : null}
      </div>
      <div className="setting-field-control">{children}</div>
    </div>
  );
}

function NumberField({ value, min, max, step = 1, unit, onChange, onBlur }) {
  return (
    <div className="number-field">
      <input
        type="number"
        value={value ?? ''}
        min={min}
        max={max}
        step={step}
        onChange={(event) => {
          const raw = event.target.value;
          onChange(raw === '' ? null : Number(raw));
        }}
        onBlur={onBlur}
      />
      {unit ? <span className="number-unit">{unit}</span> : null}
    </div>
  );
}

function Toggle({ checked, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      className={`rocker ${checked ? 'is-on' : 'is-off'}`}
      onClick={() => onChange(!checked)}
    >
      <span className="rocker-half rocker-half-on">ON</span>
      <span className="rocker-half rocker-half-off">OFF</span>
    </button>
  );
}

export default function SettingsPanel({ config, calibration, setConfigField, patchConfig }) {
  const [activeTab, setActiveTab] = useState('detection');

  const blurPatch = (key) => () => patchConfig({ [key]: config[key] });

  const numberField = (key, fallback, props = {}) => (
    <NumberField
      value={config[key]}
      onChange={(v) => setConfigField(key, v ?? fallback)}
      onBlur={blurPatch(key)}
      {...props}
    />
  );

  const depthBandText = calibration &&
    calibration.depth_low_mm != null &&
    calibration.depth_high_mm != null
    ? `${Math.round(calibration.depth_low_mm)} - ${Math.round(calibration.depth_high_mm)} mm`
    : 'Not calibrated';

  const tabs = [
    { key: 'detection', label: 'Detection', icon: <FlaskIcon size={13} /> },
    { key: 'tracking', label: 'Tracking', icon: <TracksIcon size={13} /> },
    { key: 'display', label: 'Display', icon: <EyeIcon size={13} /> },
  ];

  return (
    <section className="panel side-card settings-panel">
     <div className="panel-head">
  <span className="panel-title">
    <SettingsIcon size={15} /> Settings
  </span>

  {calibration ? (
    <div className="calibration-summary">
      <span className="calibration-summary-item">
        <small>Calibrated area</small>
        <strong>
          {Math.round(calibration.area_px || 0).toLocaleString()} px²
        </strong>
      </span>

      <span className="calibration-summary-item">
        <small>Separation</small>
        <strong>
          {Number(calibration.separation || 0).toFixed(1)}
        </strong>
      </span>
    </div>
  ) : null}
</div>

      <div className="settings-tabs" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`settings-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'detection' ? (
        <div className="panel-body settings-grid">
          <Field label="Area tolerance" hint="Accepted single-roll silhouette variation">
            {numberField('area_tolerance', 40, { min: 10, max: 80, unit: '%' })}
          </Field>
          <Field label="Contrast threshold" hint="Higher values reject more background">
            {numberField('threshold_fraction', 45, { min: 15, max: 85, unit: '%' })}
          </Field>
          <Field label="Use depth band" hint="Filter detections using calibrated depth">
            <Toggle
              checked={Boolean(config.use_depth)}
              onChange={(checked) => {
                setConfigField('use_depth', checked);
                patchConfig({ use_depth: checked });
              }}
            />
          </Field>
          <Field label="Depth extra" hint="Extra depth tolerance around the calibrated band">
            {numberField('depth_extra_mm', 100, { min: 0, max: 500, unit: 'mm' })}
          </Field>
          <Field label="Max merged rolls" hint="Largest accepted merged contour">
            {numberField('max_merged_units', 3, { min: 1, max: 10 })}
          </Field>
          <Field label="Depth band" hint="Calibrated depth range used for filtering">
            <div className="readonly-value">{depthBandText}</div>
          </Field>
          {/* {calibration ? (
            <div className="calibration-result">
              <span className="calibration-result-item">
                <small>Calibrated area</small>
                <strong>{Math.round(calibration.area_px || 0).toLocaleString()} px²</strong>
              </span>
              <span className="calibration-result-item">
                <small>Separation</small>
                <strong>{Number(calibration.separation || 0).toFixed(1)}</strong>
              </span>
            </div>
          ) : null} */}
        </div>
      ) : null}

      {activeTab === 'tracking' ? (
        <div className="panel-body settings-grid">
          <Field label="Match distance" hint="Maximum tracker association distance">
            {numberField('match_distance', 90, { min: 20, max: 250, unit: 'px' })}
          </Field>
          <Field label="Keep missed frames" hint="Frames to retain a temporarily missing track">
            {numberField('max_missed', 12, { min: 1, max: 40 })}
          </Field>
          <Field label="Confirm frames" hint="Hits required before line-cross counting">
            {numberField('min_hits', 3, { min: 1, max: 10 })}
          </Field>
          <Field label="Line hysteresis" hint="Deadband to avoid repeated side changes">
            {numberField('hysteresis_px', 8, { min: 1, max: 40, step: 0.5, unit: 'px' })}
          </Field>
        </div>
      ) : null}

      {activeTab === 'display' ? (
        <div className="panel-body settings-grid display-grid">
          {[
            ['show_detections', 'Accepted outlines', 'Show contours that pass the roll filters'],
            ['show_ids', 'Track IDs', 'Overlay tracker IDs on active detections'],
            ['show_mask', 'Binary mask', 'Show the detection mask inside the camera image'],
          ].map(([key, label, hint]) => (
            <Field key={key} label={label} hint={hint}>
              <Toggle
                checked={Boolean(config[key])}
                onChange={(checked) => {
                  setConfigField(key, checked);
                  patchConfig({ [key]: checked });
                }}
              />
            </Field>
          ))}
        </div>
      ) : null}
    </section>
  );
}
