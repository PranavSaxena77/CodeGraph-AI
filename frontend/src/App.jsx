import { useEffect, useState } from 'react'

import AppShell from './components/AppShell.jsx'
import QueryWorkspace from './components/QueryWorkspace.jsx'
import RepositoryWorkspace from './components/RepositoryWorkspace.jsx'
import SystemStatus from './components/SystemStatus.jsx'
import { getHealth, getReadiness } from './services/healthApi.js'
import { analyzeSnapshot, askRepository, buildVectorIndex, persistGraph, registerRepository } from './services/repositoryApi.js'

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

  useEffect(() => {
    let active = true
    getHealth().then((data) => active && setHealth({ loading: false, data, error: '' })).catch((error) => active && setHealth({ loading: false, data: null, error: error.message }))
    getReadiness().then((data) => active && setReadiness({ loading: false, data, error: '' })).catch((error) => active && setReadiness({ loading: false, data: null, error: error.message }))
    return () => { active = false }
  }, [])

  async function handleRegister(githubUrl) {
    setRegistrationState({ loading: true, error: '' })
    try {
      const result = await registerRepository(githubUrl)
      setRepository(result.repository)
      setSnapshot(result.snapshot)
      setStages({ ...initialStages, ingestion: 'complete' })
      setRegistrationState(idleRequest)
    } catch (error) {
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
      setAnalysisSummary({ symbols: analysis.symbols.length, nodes: graph.node_count, relationships: graph.relationship_count, chunks: vector.chunk_count })
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
  if (activeView === 'repository') content = <RepositoryWorkspace repository={repository} snapshot={snapshot} stages={stages} registrationState={registrationState} analysisState={analysisState} analysisSummary={analysisSummary} onRegister={handleRegister} onAnalyze={handleAnalyze} />
  if (activeView === 'intelligence') content = <QueryWorkspace repository={repository} snapshot={snapshot} indexReady={indexReady} queryState={queryState} onAsk={handleAsk} onNavigateRepository={() => setActiveView('repository')} />
  if (activeView === 'system') content = <SystemStatus health={health} readiness={readiness} />

  const connectionState = health.loading ? 'loading' : health.data ? 'available' : 'unavailable'
  return <AppShell activeView={activeView} onNavigate={setActiveView} repository={repository} snapshot={snapshot} indexReady={indexReady} connectionState={connectionState}>{content}</AppShell>
}

export default App
