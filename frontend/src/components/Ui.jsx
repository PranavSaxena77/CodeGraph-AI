export function Spinner({ label }) {
  return <span className="spinner" aria-label={label} role={label ? 'img' : undefined} />
}

const iconPaths = {
  repository: <><path d="M3 5.5h6l2 2h10v11H3z" /><path d="M3 9h18" /></>,
  intelligence: <><path d="M12 3a6 6 0 0 0-3.5 10.9V17h7v-3.1A6 6 0 0 0 12 3Z" /><path d="M9 21h6M9 17h6" /></>,
  system: <><path d="M4 7h16M4 17h16" /><circle cx="8" cy="7" r="2" /><circle cx="16" cy="17" r="2" /></>,
  refresh: <><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></>,
  external: <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 13v7H4V6h7" /></>,
  copy: <><rect x="8" y="8" width="11" height="11" rx="1" /><path d="M16 8V5H5v11h3" /></>,
  graph: <><circle cx="6" cy="6" r="2" /><circle cx="18" cy="6" r="2" /><circle cx="12" cy="18" r="2" /><path d="m8 7 3 9m5-9-3 9M8 6h8" /></>,
  layers: <><path d="m12 3 9 5-9 5-9-5z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>,
  code: <><path d="m8 9-4 3 4 3m8-6 4 3-4 3M14 5l-4 14" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  branch: <><circle cx="6" cy="5" r="2" /><circle cx="18" cy="7" r="2" /><circle cx="6" cy="19" r="2" /><path d="M6 7v10M8 7h4a6 6 0 0 1 6 6v-4" /></>,
  activity: <path d="M3 12h4l2.5-6 5 12 2.5-6h4" />,
  expand: <><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" /><path d="m3 8 6-6m12 6-6-6M3 16l6 6m12-6-6 6" /></>,
  close: <path d="m5 5 14 14M19 5 5 19" />,
}

export function Icon({ name, size = 16 }) {
  return <svg aria-hidden="true" className="icon" fill="none" height={size} viewBox="0 0 24 24" width={size} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7">{iconPaths[name]}</svg>
}

export function StatusIndicator({ state, label, pulse = false }) {
  return (
    <span className="status-indicator">
      <span className={`signal signal--${state} ${pulse ? 'signal--pulse' : ''}`} aria-hidden="true" />
      <span>{label}</span>
    </span>
  )
}

export function ErrorPanel({ title, message, actionLabel, onAction, compact = false }) {
  return (
    <div className={`notice notice--error ${compact ? '' : 'notice--standalone'}`} role="alert">
      <div className="notice__copy"><strong>{title}</strong><span>{message}</span></div>
      {onAction && <button className="button button--secondary" onClick={onAction} type="button">{actionLabel ?? 'Retry'}</button>}
    </div>
  )
}
