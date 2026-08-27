import { useEffect, useLayoutEffect, useState } from 'react'

import AppShell from './components/AppShell.jsx'
import QueryWorkspace from './components/QueryWorkspace.jsx'
import RepositoryWorkspace from './components/RepositoryWorkspace.jsx'
import SystemStatus from './components/SystemStatus.jsx'
import { getHealth, getReadiness } from './services/healthApi.js'
import { analyzeSnapshot, askRepository, buildVectorIndex, getGraphPreview, getPipelineOperation, persistGraph, registerRepository } from './services/repositoryApi.js'
import { applyTheme, getInitialTheme } from './theme.js'

const initialStages = { ingestion: 'pending', analysis: 'pending', graph: 'pending', vector: 'pending', ready: 'pending' }
const idleRequest = { loading: false, error: '' }
const STALE_OPERATION_MESSAGE = 'Live activity ended because the backend operation is no longer available.'

function App() {
  const [activeView, setActiveView] = useState('repository')
  const [repository, setRepository] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [stages, setStages] = useState(initialStages)
  const [registrationState, setRegistrationState] = useState(idleRequest)
  const [analysisState, setAnalysisState] = useState(idleRequest)
  const [analysisSummary, setAnalysisSummary] = useState(null)
  const [operation, setOperation] = useState({ id: '', data: null, error: '' })
  const [graphPreview, setGraphPreview] = useState({ loading: false, data: null, error: '' })
  const [queryState, setQueryState] = useState({ ...idleRequest, result: null })
  const [health, setHealth] = useState({ loading: true, data: null, error: '' })
  const [readiness, setReadiness] = useState({ loading: true, data: null, error: '' })
  const [lastHealthRefresh, setLastHealthRefresh] = useState(null)
  const [theme, setTheme] = useState(getInitialTheme)

  useLayoutEffect(() => {
    applyTheme(theme)
    if (theme !== 'system' || !window.matchMedia) return undefined
    const media = window.matchMedia('(prefers-color-scheme: light)')
    const syncSystemTheme = () => applyTheme('system')
    media.addEventListener?.('change', syncSystemTheme)
    return () => media.removeEventListener?.('change', syncSystemTheme)
  }, [theme])

  useEffect(() => {
    let active = true
    refreshHealth(() => active)
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!operation.id || (!registrationState.loading && !analysisState.loading)) return undefined
    let active = true
    const refresh = async () => {
      try {
        const data = await getPipelineOperation(operation.id)
        if (!active) return
        setOperation((current) => ({ ...current, data, error: '' }))
        setStages({ ...data.stages, ready: data.stages.vector === 'complete' ? 'complete' : 'pending' })
      } catch (error) {
        if (!active) return
        if (error.status === 404) retireOperation(operation.id)
        else setOperation((current) => ({ ...current, error: error.message }))
      }
    }
    refresh()
    const interval = window.setInterval(refresh, 350)
    return () => { active = false; window.clearInterval(interval) }
  }, [analysisState.loading, operation.id, registrationState.loading])

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
    const operationId = createOperationId()
    setOperation({ id: operationId, data: null, error: '' })
    setGraphPreview({ loading: false, data: null, error: '' })
    setRegistrationState({ loading: true, error: '' })
    setStages({ ...initialStages, ingestion: 'running' })
    try {
      const result = await registerRepository(githubUrl, operationId)
      setRepository(result.repository)
      setSnapshot(result.snapshot)
      setStages({ ...initialStages, ingestion: 'complete' })
      await refreshOperation(operationId)
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
      const analysis = await analyzeSnapshot(repositoryId, snapshotId, operation.id)
      setAnalysisSummary(buildStructuralSummary(analysis))
      activeStage = 'graph'
      setStages((current) => ({ ...current, analysis: 'complete', graph: 'running' }))

      const graph = await persistGraph(repositoryId, snapshotId, operation.id)
      setAnalysisSummary((current) => ({ ...current, nodes: graph.node_count, relationships: graph.relationship_count }))
      setGraphPreview({ loading: true, data: null, error: '' })
      try {
        const preview = await getGraphPreview(repositoryId, snapshotId)
        setGraphPreview({ loading: false, data: preview, error: '' })
      } catch (error) {
        setGraphPreview({ loading: false, data: null, error: error.message })
      }
      activeStage = 'vector'
      setStages((current) => ({ ...current, graph: 'complete', vector: 'running' }))

      const vector = await buildVectorIndex(repositoryId, snapshotId, operation.id)
      setStages({ ingestion: 'complete', analysis: 'complete', graph: 'complete', vector: 'complete', ready: 'complete' })
      setAnalysisSummary(buildAnalysisSummary(analysis, graph, vector))
      await refreshOperation(operation.id)
      setAnalysisState(idleRequest)
    } catch (error) {
      setStages((current) => ({ ...current, [activeStage]: 'failed' }))
      const stageLabel = { analysis: 'Analysis', graph: 'Graph indexing', vector: 'Vector indexing' }[activeStage]
      setAnalysisState({ loading: false, error: error.message, failedStage: stageLabel })
    }
  }

  async function refreshOperation(operationId) {
    try {
      const data = await getPipelineOperation(operationId)
      setOperation({ id: operationId, data, error: '' })
      setStages({ ...data.stages, ready: data.stages.vector === 'complete' ? 'complete' : 'pending' })
    } catch (error) {
      if (error.status === 404) retireOperation(operationId)
      else setOperation((current) => ({ ...current, error: error.message }))
    }
  }

  function retireOperation(operationId) {
    setOperation((current) => current.id === operationId
      ? { id: '', data: null, error: STALE_OPERATION_MESSAGE }
      : current)
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
  if (activeView === 'repository') content = <RepositoryWorkspace repository={repository} snapshot={snapshot} stages={stages} operation={operation} graphPreview={graphPreview} registrationState={registrationState} analysisState={analysisState} analysisSummary={analysisSummary} onRegister={handleRegister} onAnalyze={handleAnalyze} onOpenIntelligence={() => setActiveView('intelligence')} />
  if (activeView === 'intelligence') content = <QueryWorkspace repository={repository} snapshot={snapshot} indexReady={indexReady} queryState={queryState} onAsk={handleAsk} onNavigateRepository={() => setActiveView('repository')} />
  if (activeView === 'system') content = <SystemStatus health={health} readiness={readiness} lastRefresh={lastHealthRefresh} onRefresh={() => refreshHealth()} />

  const connectionState = health.loading ? 'loading' : health.data ? 'available' : 'unavailable'
  return <AppShell activeView={activeView} onNavigate={setActiveView} connectionState={connectionState} repository={repository} health={health} readiness={readiness} theme={theme} onThemeChange={setTheme} onRefresh={() => refreshHealth()} refreshing={health.loading || readiness.loading}>{content}</AppShell>
}

function createOperationId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `operation-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

function buildStructuralSummary(analysis) {
  const counts = { files: 0, classes: 0, functions: 0, methods: 0 }
  analysis.symbols.forEach((symbol) => {
    const key = symbol.symbol_type === 'file' ? 'files' : `${symbol.symbol_type}s`
    if (key in counts) counts[key] += 1
  })
  return {
    ...counts,
    imports: analysis.imports.length,
    inheritances: analysis.inheritances.length,
    resolvedCalls: analysis.calls.filter((call) => call.resolution === 'resolved').length,
    diagnostics: analysis.diagnostics.length,
  }
}

function buildAnalysisSummary(analysis, graph, vector) {
  return {
    ...buildStructuralSummary(analysis),
    nodes: graph.node_count,
    relationships: graph.relationship_count,
    chunks: vector.chunk_count,
    vectors: vector.chunk_count,
    dimension: vector.vector_dimension,
  }
}

export default App
