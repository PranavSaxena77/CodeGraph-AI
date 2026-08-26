import { Icon, Spinner } from './Ui.jsx'

const navigationGroups = [
  { label: 'Workspace', items: [{ id: 'repository', label: 'Repository', icon: 'repository' }, { id: 'intelligence', label: 'Intelligence', icon: 'intelligence' }] },
  { label: 'Operations', items: [{ id: 'system', label: 'System', icon: 'system' }] },
]

function ThemeSwitcher({ theme, onChange }) {
  return <div className="theme-switcher" role="group" aria-label="Theme">{['dark', 'light'].map((value) => <button aria-pressed={theme === value} key={value} onClick={() => onChange(value)} type="button">{value}</button>)}</div>
}

function TopBar({ theme, onThemeChange, onRefresh, refreshing }) {
  return <header className="top-bar"><div className="top-bar__brand"><span>CodeGraph AI</span><code>v0.1.0</code></div><div className="top-bar__actions"><ThemeSwitcher theme={theme} onChange={onThemeChange} /><button aria-label="Refresh API status" className="icon-button" disabled={refreshing} onClick={onRefresh} type="button">{refreshing ? <Spinner /> : <Icon name="refresh" />}</button></div></header>
}

function Sidebar({ activeView, onNavigate, connectionState }) {
  const statusLabel = connectionState === 'available' ? 'API connected' : connectionState === 'loading' ? 'Checking API' : 'API unavailable'
  return <aside className="sidebar"><div className="wordmark"><span className="wordmark__mark">CG</span><div><strong>CodeGraph</strong><small>Repository intelligence</small></div></div><nav className="nav" aria-label="Workspace">{navigationGroups.map((group) => <div className="nav__group" key={group.label}><span className="nav__group-label">{group.label}</span>{group.items.map((item) => <button aria-current={activeView === item.id ? 'page' : undefined} className={`nav__item ${activeView === item.id ? 'nav__item--active' : ''}`} key={item.id} onClick={() => onNavigate(item.id)} type="button"><Icon name={item.icon} /><span>{item.label}</span></button>)}</div>)}</nav><div className="sidebar__footer"><div><span className={`signal signal--${connectionState}`} aria-hidden="true" /><span>Backend API</span></div><strong>{statusLabel}</strong><code>API · v0.1.0</code></div></aside>
}

export default function AppShell({ activeView, onNavigate, connectionState, theme, onThemeChange, onRefresh, refreshing, children }) {
  return <div className="app-shell"><TopBar theme={theme} onThemeChange={onThemeChange} onRefresh={onRefresh} refreshing={refreshing} /><Sidebar activeView={activeView} onNavigate={onNavigate} connectionState={connectionState} /><main className="workspace">{children}</main></div>
}
