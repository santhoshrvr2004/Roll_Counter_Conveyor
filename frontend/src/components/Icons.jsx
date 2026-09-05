import React from 'react';

const base = (props) => ({
  width: props.size || 16,
  height: props.size || 16,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
  style: props.style,
});

export const CameraIcon = (p) => (
  <svg {...base(p)}>
    <path d="M4 8h3l2-2h6l2 2h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z" />
    <circle cx="12" cy="13" r="3.5" />
  </svg>
);

export const GaugeIcon = (p) => (
  <svg {...base(p)}>
    <path d="M4 14a8 8 0 1 1 16 0" />
    <path d="M12 14l3.5-3.5" />
    <path d="M3 18h18" />
  </svg>
);

export const TargetIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="8" />
    <circle cx="12" cy="12" r="3" />
    <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
  </svg>
);

export const CrosshairIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="7" />
    <path d="M12 5v4M12 15v4M5 12h4M15 12h4" />
  </svg>
);

export const ArrowLeftIcon = (p) => (
  <svg {...base(p)}>
    <path d="M19 12H5M11 6l-6 6 6 6" />
  </svg>
);

export const ArrowRightIcon = (p) => (
  <svg {...base(p)}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);

export const RefreshIcon = (p) => (
  <svg {...base(p)}>
    <path d="M20 12a8 8 0 1 1-2.34-5.66" />
    <path d="M20 4v4h-4" />
  </svg>
);

export const PlayIcon = (p) => (
  <svg {...base(p)}>
    <path d="M8 5.5v13l11-6.5z" />
  </svg>
);

export const PauseIcon = (p) => (
  <svg {...base(p)}>
    <path d="M8 5v14M16 5v14" />
  </svg>
);

export const PlugIcon = (p) => (
  <svg {...base(p)}>
    <path d="M9 7V3M15 7V3" />
    <path d="M6 7h12v4a6 6 0 0 1-6 6 6 6 0 0 1-6-6z" />
    <path d="M12 17v4" />
  </svg>
);

export const DisconnectIcon = (p) => (
  <svg {...base(p)}>
    <path d="M9 7V4M15 7V4" />
    <path d="M6 7h12v4a6 6 0 0 1-6 6 6 6 0 0 1-6-6z" />
    <path d="M12 17v3" />
    <path d="M4 21L20 5" />
  </svg>
);

export const SettingsIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.01A1.7 1.7 0 0 0 10 3.09V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.01A1.7 1.7 0 0 0 20.91 10H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.56 1.03z" />
  </svg>
);

export const CheckIcon = (p) => (
  <svg {...base(p)}>
    <path d="M4.5 12.5l5 5L19.5 7" />
  </svg>
);

export const InfoIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8h.01M12 11v5" />
  </svg>
);

export const TrashIcon = (p) => (
  <svg {...base(p)}>
    <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-7-0-6" />
  </svg>
);

export const ExpandIcon = (p) => (
  <svg {...base(p)}>
    <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
  </svg>
);

export const BoxIcon = (p) => (
  <svg {...base(p)}>
    <rect x="4" y="6" width="16" height="12" rx="1.5" />
    <path d="M4 12h16" />
  </svg>
);

export const LineIcon = (p) => (
  <svg {...base(p)}>
    <path d="M4 18L20 6" />
    <circle cx="4" cy="18" r="1.6" fill="currentColor" />
    <circle cx="20" cy="6" r="1.6" fill="currentColor" />
  </svg>
);

export const StopIcon = (p) => (
  <svg {...base(p)}>
    <rect x="6" y="6" width="12" height="12" rx="1.5" />
  </svg>
);

export const FlaskIcon = (p) => (
  <svg {...base(p)}>
    <path d="M10 3v6L4.5 18a2 2 0 0 0 1.7 3h11.6a2 2 0 0 0 1.7-3L14 9V3" />
    <path d="M8.5 3h7" />
  </svg>
);

export const TracksIcon = (p) => (
  <svg {...base(p)}>
    <path d="M4 17c4 0 4-10 8-10s4 10 8 10" />
    <circle cx="4" cy="17" r="1.6" fill="currentColor" />
    <circle cx="20" cy="17" r="1.6" fill="currentColor" />
  </svg>
);

export const EyeIcon = (p) => (
  <svg {...base(p)}>
    <path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z" />
    <circle cx="12" cy="12" r="2.8" />
  </svg>
);

export const ChevronDownIcon = (p) => (
  <svg {...base(p)}>
    <path d="M6 9l6 6 6-6" />
  </svg>
);

export const ShieldIcon = (p) => (
  <svg {...base(p)}>
    <path d="M12 3l7 3v5c0 4.6-3 8.4-7 10-4-1.6-7-5.4-7-10V6z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);
