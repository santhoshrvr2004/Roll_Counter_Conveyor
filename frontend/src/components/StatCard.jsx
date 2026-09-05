import React from 'react';

export default function StatCard({ label, value, icon, tone = 'blue' }) {
  return (
    <div className={`stat-card stat-${tone}`}>
      <div className={`stat-card-icon stat-icon-${tone}`}>{icon}</div>
      <div className="stat-card-copy">
        <span className="stat-card-label">{label}</span>
        <strong className="stat-card-value">{value ?? 0}</strong>
      </div>
    </div>
  );
}
