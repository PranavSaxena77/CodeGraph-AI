import { useEffect, useLayoutEffect, useState } from 'react'

import AppShell from './components/AppShell.jsx'
import QueryWorkspace from './components/QueryWorkspace.jsx'
import RepositoryWorkspace from './components/RepositoryWorkspace.jsx'
import SystemStatus from './components/SystemStatus.jsx'
import { getHealth, getReadiness } from './services/healthApi.js'
import { analyzeSnapshot, askRepository, buildVectorIndex, persistGraph, registerRepository } from './services/repositoryApi.js'
import { applyTheme, getInitialTheme } from './theme.js'

const initialStages = { ingestion: 'pending', analysis: 'pending', graph: 'pending', vector: 'pending', ready: 'pending' }
const idleRequest = { loading: false, error: '' }

function App() {
  const [activeView, setActiveView] = useState('repository')
  const [repository, setRepository] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [stages, setStages] = useState(initialStages)
  const [registrationState, setRegistrationState] = useState(idleRequest)
  const [analysisState, setAnalysisState] = useState(idleRequest)
  const [analysisSummary, setAnalysisSummary] = useState(null)
  const [queryState, setQueryState] = useState({ ...idleRequest, result: null })
  const [health, setHealth] = useState({ loading: true, data: null, error: '' })
  const [readiness, setReadiness] = useState({ loading: true, data: null, error: '' })
  const [lastHealthRefresh, setLastHealthRefresh] = useState(null)
  const [theme, setTheme] = useState(getInitialTheme)

  useLayoutEffect(() => { applyTheme(theme) }, [theme])

  useEffect(() => {
    let active = true
    refreshHealth(() => active)
    return () => { active = false }
  }, [])

  async function refreshHealth(isActive = () => true) {
    setHealth((current) => ({ ...current, loading: true, error: '' }))
    setReadiness((current) => ({ ...current, loading: true, error: '' }))
    const [healthResult, readinessResult] = await Promise.allSettled([getHealth(), getReadiness()])
    if (!isActive()) return

    setHealth(healthResult.status === 'fulfilled'
      ? { loading: false, data: healthResult.value, error: '' }
      : { loading: false, data: null, error: healthResult.reason.message })
    setReadiness(readinessResult.status === 'fulfilled'
      ? { loading: false, data: readinessResult.value, error: '' }
      : { loading: false, data: null, error: readinessResult.reason.message })
    setLastHealthRefresh(new Date())
  }

  async function handleRegister(githubUrl) {
    setRegistrationState({ loading: true, error: '' })
    setStages({ ...initialStages, ingestion: 'running' })
    try {
      const result = await registerRepository(githubUrl)
      setRepository(result.repository)
      setSnapshot(result.snapshot)
      setStages({ ...initialStages, ingestion: 'complete' })
      setRegistrationState(idleRequest)
    } catch (error) {
      setStages({ ...initialStages, ingestion: 'failed' })
      setRegistrationState({ loading: false, error: error.message })
    }
  }

  async function handleAnalyze() {
    const repositoryId = repository.id
    const snapshotId = snapshot.id
    let activeStage = 'analysis'
    setAnalysisState({ loading: true, error: '', failedStage: '' })
    setAnalysisSummary(null)

    try {
      setStages((current) => ({ ...current, analysis: 'running' }))
      const analysis = await analyzeSnapshot(repositoryId, snapshotId)
      activeStage = 'graph'
      setStages((current) => ({ ...current, analysis: 'complete', graph: 'running' }))

      const graph = await persistGraph(repositoryId, snapshotId)
      activeStage = 'vector'
      setStages((current) => ({ ...current, graph: 'complete', vector: 'running' }))

      const vector = await buildVectorIndex(repositoryId, snapshotId)
      setStages({ ingestion: 'complete', analysis: 'complete', graph: 'complete', vector: 'complete', ready: 'complete' })
      setAnalysisSummary({ symbols: analysis.symbols.length, nodes: graph.node_count, relationships: graph.relationship_count, chunks: vector.chunk_count, completedAt: new Date().toISOString() })
      setAnalysisState(idleRequest)
    } catch (error) {
      setStages((current) => ({ ...current, [activeStage]: 'failed' }))
      const stageLabel = { analysis: 'Analysis', graph: 'Graph indexing', vector: 'Vector indexing' }[activeStage]
      setAnalysisState({ loading: false, error: error.message, failedStage: stageLabel })
    }
  }

  async function handleAsk(question) {
    setQueryState({ loading: true, error: '', result: null })
    try {
      const result = await askRepository(repository.id, snapshot.id, question)
      setQueryState({ loading: false, error: '', result })
    } catch (error) {
      setQueryState({ loading: false, error: error.message, result: null })
    }
  }

  const indexReady = stages.ready === 'complete'
  let content
  if (activeView === 'repository') content = <RepositoryWorkspace repository={repository} snapshot={snapshot} stages={stages} registrationState={registrationState} analysisState={analysisState} analysisSummary={analysisSummary} onRegister={handleRegister} onAnalyze={handleAnalyze} onOpenIntelligence={() => setActiveView('intelligence')} />
  if (activeView === 'intelligence') content = <QueryWorkspace repository={repository} snapshot={snapshot} indexReady={indexReady} queryState={queryState} onAsk={handleAsk} onNavigateRepository={() => setActiveView('repository')} />
  if (activeView === 'system') content = <SystemStatus health={health} readiness={readiness} lastRefresh={lastHealthRefresh} onRefresh={() => refreshHealth()} />

  const connectionState = health.loading ? 'loading' : health.data ? 'available' : 'unavailable'
  return <AppShell activeView={activeView} onNavigate={setActiveView} connectionState={connectionState} theme={theme} onThemeChange={setTheme} onRefresh={() => refreshHealth()} refreshing={health.loading || readiness.loading}>{content}</AppShell>
}

export default App
