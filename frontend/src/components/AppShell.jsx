import { Icon, Spinner } from './Ui.jsx'
import { getApiBaseUrl } from '../services/apiClient.js'
import { THEME_OPTIONS } from '../theme.js'

const navigationGroups = [
  { label: 'Workspace', items: [{ id: 'repository', label: 'Repository', icon: 'repository' }, { id: 'intelligence', label: 'Intelligence', icon: 'intelligence' }] },
  { label: 'Operations', items: [{ id: 'system', label: 'System', icon: 'system' }] },
]

function ThemeSwitcher({ theme, onChange }) {
  return <div className="theme-switcher" role="group" aria-label="Theme preference">{THEME_OPTIONS.map((value) => <button aria-label={`${value} theme`} aria-pressed={theme === value} key={value} onClick={() => onChange(value)} title={`Use ${value} theme`} type="button">{value}</button>)}</div>
}

function TopBar({ repository, theme, onThemeChange, onRefresh, refreshing }) {
  return <header className="top-bar"><div className="top-bar__brand"><span className="top-bar__mark">CG</span><strong>CodeGraph AI</strong>{repository && <><span className="top-bar__divider" aria-hidden="true" /><span className="top-bar__repository"><Icon name="repository" size={15} />{repository.owner} / {repository.name}</span></>}</div><div className="top-bar__actions"><div className="top-bar__repository-actions"><ThemeSwitcher theme={theme} onChange={onThemeChange} />{repository && <a className="button button--secondary top-bar__github" href={repository.github_url} target="_blank" rel="noreferrer">View on GitHub <Icon name="external" size={14} /></a>}</div><button aria-label="Refresh API status" className="icon-button" disabled={refreshing} onClick={onRefresh} title="Refresh API status" type="button">{refreshing ? <Spinner /> : <Icon name="refresh" />}</button></div></header>
}

function Sidebar({ activeView, onNavigate, connectionState, health, readiness }) {
  const statusLabel = connectionState === 'available' ? 'API connected' : connectionState === 'loading' ? 'Checking API' : 'API unavailable'
  const dependencyState = (name) => readiness.loading ? 'loading' : readiness.data?.dependencies?.[name]?.status === 'ready' ? 'available' : 'unavailable'
  const version = health.data?.version ?? '0.1.0'
  const services = [
    ['Backend', connectionState],
    ['MongoDB', dependencyState('mongodb')],
    ['Neo4j', dependencyState('neo4j')],
  ]
  return <aside className="sidebar"><div className="sidebar__context"><span className="sidebar__mark" aria-hidden="true">&lt;/&gt;</span><strong>CodeGraph AI</strong><small>v{version}</small></div><nav className="nav" aria-label="Workspace">{navigationGroups.map((group) => <div className="nav__group" key={group.label}><span className="nav__group-label">{group.label}</span>{group.items.map((item) => <button aria-current={activeView === item.id ? 'page' : undefined} className={`nav__item ${activeView === item.id ? 'nav__item--active' : ''}`} key={item.id} onClick={() => onNavigate(item.id)} type="button"><Icon name={item.icon} /><span>{item.label}</span></button>)}</div>)}</nav><div className="sidebar__footer"><div className="sidebar__api"><span className={`signal signal--${connectionState}`} aria-hidden="true" /><strong>{statusLabel}</strong></div><code title={getApiBaseUrl()}>{getApiBaseUrl()}</code><div className="sidebar__services">{services.map(([name, state]) => <span key={name}><i className={`signal signal--${state}`} aria-hidden="true" />{name} {state === 'available' ? 'Healthy' : state === 'loading' ? 'Checking' : 'Unavailable'}</span>)}</div><small>v{version}</small></div></aside>
}

export default function AppShell({ activeView, onNavigate, connectionState, repository, health, readiness, theme, onThemeChange, onRefresh, refreshing, children }) {
  return <div className="app-shell"><TopBar repository={repository} theme={theme} onThemeChange={onThemeChange} onRefresh={onRefresh} refreshing={refreshing} /><Sidebar activeView={activeView} onNavigate={onNavigate} connectionState={connectionState} health={health} readiness={readiness} /><main className="workspace">{children}</main></div>
}
