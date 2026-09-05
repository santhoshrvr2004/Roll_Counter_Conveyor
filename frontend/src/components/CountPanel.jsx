import React from 'react';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  GaugeIcon,
  PauseIcon,
  PlayIcon,
  RefreshIcon,
} from './Icons';

export default function CountPanel({ status, setupComplete, busy, onToggleCounting, onReset }) {
  const counting = Boolean(status?.counting);

  const confirmReset = () => {
    if (window.confirm('Reset current count? Total and directional counts will return to zero.')) {
      onReset();
    }
  };

  return (
    <section className={`panel count-panel ${counting ? 'is-running' : ''}`}>
      <div className="count-panel-head">
        <div>
          <span className="eyebrow">Production count</span>
          <div className="count-state-line">
            <span className={`status-chip ${counting ? 'chip-success' : 'chip-neutral'}`}>
              {counting ? <PlayIcon size={12} /> : <PauseIcon size={12} />}
              {counting ? 'Live' : 'Stopped'}
            </span>
            <span className="muted">Crossings inside gate</span>
          </div>
        </div>
        <div className="count-panel-icon"><GaugeIcon size={17} /></div>
      </div>

      <div className="count-main-value">{status?.total ?? 0}</div>

      <div className="direction-mini-grid">
        <div className="direction-mini direction-a">
          <span><ArrowRightIcon size={13} /> A → B</span>
          <strong>{status?.negative_to_positive ?? 0}</strong>
        </div>
        <div className="direction-mini direction-b">
          <span><ArrowLeftIcon size={13} /> B → A</span>
          <strong>{status?.positive_to_negative ?? 0}</strong>
        </div>
      </div>

      <div className="count-actions">
        <button
          type="button"
          className={`button ${counting ? 'button-danger-outline' : 'button-primary'} count-toggle`}
          disabled={busy || (!counting && !setupComplete)}
          onClick={onToggleCounting}
        >
          {counting ? <PauseIcon size={14} /> : <PlayIcon size={14} />}
          {counting ? 'Stop' : 'Start Counting'}
        </button>
        <button
          type="button"
          className="button button-outline"
          disabled={busy}
          onClick={confirmReset}
        >
          <RefreshIcon size={14} />
          Reset
        </button>
      </div>
    </section>
  );
}
