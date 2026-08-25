const navigationGroups = [
  {
    label: 'Workspace',
    items: [
      { id: 'repository', label: 'Repository', detail: 'Setup and indexing' },
      { id: 'intelligence', label: 'Intelligence', detail: 'Evidence query' },
    ],
  },
  {
    label: 'Operations',
    items: [{ id: 'system', label: 'System', detail: 'Service health' }],
  },
]

function Sidebar({ activeView, onNavigate, connectionState }) {
  return (
    <aside className="sidebar">
      <div className="wordmark">
        <span className="wordmark__mark" aria-hidden="true">CG</span>
        <span>CodeGraph AI</span>
      </div>
      <nav className="nav" aria-label="Workspace">
        {navigationGroups.map((group) => (
          <div className="nav__group" key={group.label}>
            <span className="nav__group-label">{group.label}</span>
            {group.items.map((item) => (
              <button
                aria-current={activeView === item.id ? 'page' : undefined}
                className={`nav__item ${activeView === item.id ? 'nav__item--active' : ''}`}
                key={item.id}
                onClick={() => onNavigate(item.id)}
                type="button"
              >
                <span>{item.label}</span>
                <small>{item.detail}</small>
              </button>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar__footer">
        <div className="sidebar__connection">
          <span className={`signal signal--${connectionState}`} aria-hidden="true" />
          <span>{connectionState === 'available' ? 'API connected' : connectionState === 'loading' ? 'Checking API' : 'API unavailable'}</span>
        </div>
        <code>v0.1.0</code>
      </div>
    </aside>
  )
}

function WorkspaceHeader({ repository, snapshot, indexReady }) {
  const repositoryName = repository ? `${repository.owner}/${repository.name}` : 'No repository selected'
  const status = !repository ? 'Not configured' : indexReady ? 'Index ready' : 'Setup required'

  return (
    <header className="workspace-header">
      <div className="workspace-header__identity">
        <span className="workspace-header__label">CodeGraph / Repository</span>
        <strong>{repositoryName}</strong>
      </div>
      <div className="workspace-header__context" aria-label="Repository context">
        <span><small>Ref</small><code>{snapshot?.ref ?? '—'}</code></span>
        <span><small>Commit</small><code>{snapshot?.commit_sha?.slice(0, 7) ?? '—'}</code></span>
        <span className={`status-badge status-badge--${indexReady ? 'complete' : 'pending'}`}>{status}</span>
      </div>
    </header>
  )
}

export default function AppShell({ activeView, onNavigate, repository, snapshot, indexReady, connectionState, children }) {
  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} onNavigate={onNavigate} connectionState={connectionState} />
      <div className="workspace">
        <WorkspaceHeader repository={repository} snapshot={snapshot} indexReady={indexReady} />
        <main className="workspace__content">{children}</main>
      </div>
    </div>
  )
}
