import React from 'react';
import { CheckIcon, CrosshairIcon, TrashIcon } from './Icons';

export default function SetupPanel({
  setupItems,
  drawMode,
  setupComplete,
  onBeginDraw,
  onClear,
  busy,
}) {
  const completed = setupItems.filter((item) => item.complete).length;

  const confirmClear = () => {
    if (window.confirm('Clear the complete setup? ROI, box, line, calibration and counts will be reset.')) {
      onClear();
    }
  };

  return (
    <section className="panel side-card setup-panel">
      <div className="panel-head">
        <span className="panel-title"><CrosshairIcon size={15} /> Setup workflow</span>
        <span className="panel-head-tools">
          <span className={`status-chip ${setupComplete ? 'chip-success' : 'chip-info'}`}>
            {completed}/4
          </span>
          <button
            type="button"
            className="icon-button icon-button-danger"
            title="Clear complete setup"
            disabled={busy}
            onClick={confirmClear}
          >
            <TrashIcon size={14} />
          </button>
        </span>
      </div>

      <div className="panel-body setup-step-grid">
        {setupItems.map((item, index) => (
          <button
            key={item.key}
            type="button"
            className={`setup-step ${drawMode === item.key ? 'active' : ''} ${item.complete ? 'complete' : ''}`}
            onClick={() => onBeginDraw(item.key)}
          >
            <span className="setup-step-index">{index + 1}</span>
            <span className="setup-step-label">{item.label}</span>
            {item.complete ? (
              <span className="setup-step-check"><CheckIcon size={12} /></span>
            ) : null}
          </button>
        ))}
      </div>
    </section>
  );
}
