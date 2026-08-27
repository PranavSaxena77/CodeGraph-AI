import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.jsx'
import { INTELLIGENCE_QUESTIONS } from './components/intelligenceQuestions.js'
import { getHealth, getReadiness } from './services/healthApi.js'
import { analyzeSnapshot, askRepository, buildVectorIndex, getGraphPreview, getPipelineOperation, persistGraph, registerRepository } from './services/repositoryApi.js'

vi.mock('./services/healthApi.js', () => ({ getHealth: vi.fn(), getReadiness: vi.fn() }))
vi.mock('./services/repositoryApi.js', () => ({
  registerRepository: vi.fn(),
  analyzeSnapshot: vi.fn(),
  persistGraph: vi.fn(),
  buildVectorIndex: vi.fn(),
  getGraphPreview: vi.fn(),
  getPipelineOperation: vi.fn(),
  askRepository: vi.fn(),
}))

const registration = {
  repository: {
    id: 'repository-1',
    owner: 'octocat',
    name: 'hello-python',
    github_url: 'https://github.com/octocat/hello-python',
    default_branch: 'main',
    created_at: '2026-08-25T00:00:00Z',
  },
  snapshot: {
    id: 'snapshot-1',
    repository_id: 'repository-1',
    commit_sha: 'abcdef1234567890abcdef1234567890abcdef12',
    ref: 'main',
    status: 'ready',
    discovered_file_count: 7,
    warnings: [],
    errors: [],
    created_at: '2026-08-25T00:00:00Z',
  },
  idempotent: false,
}

const answeredQuery = {
  repository_id: 'repository-1', snapshot_id: 'snapshot-1', commit_sha: registration.snapshot.commit_sha,
  question: 'How is ingestion bounded?', outcome: 'answered', answer: 'Archives are checked against configured extraction limits.',
  cited_evidence_ids: ['E1'], limitations: ['Only the selected ingestion path was inspected.'],
  evidence: [
    { evidence_id: 'E1', chunk_id: 'chunk-1', repository_id: 'repository-1', snapshot_id: 'snapshot-1', commit_sha: registration.snapshot.commit_sha, file_path: 'backend/app/modules/ingestion/archive.py', symbol_id: 'symbol-1', symbol_name: 'extract', qualified_name: 'SafeZipExtractor.extract', symbol_type: 'method', start_line: 42, end_line: 43, content: 'def extract(self, archive):\n    self._validate_limits(archive)' },
    { evidence_id: 'E2', chunk_id: 'chunk-2', repository_id: 'repository-1', snapshot_id: 'snapshot-1', commit_sha: registration.snapshot.commit_sha, file_path: 'backend/app/core/config.py', symbol_id: 'symbol-2', symbol_name: 'Settings', qualified_name: 'Settings', symbol_type: 'class', start_line: 10, end_line: 12, content: 'class Settings:\n    max_archive_bytes = 100_000\n    max_file_bytes = 10_000' },
  ],
  retrieval_metadata: {},
}

const graphPreview = {
  nodes: [
    { id: 'snapshot-1', node_type: 'Snapshot', repository_id: 'repository-1', snapshot_id: 'snapshot-1' },
    { id: 'file-1', node_type: 'File', repository_id: 'repository-1', snapshot_id: 'snapshot-1', file_path: 'main.py' },
    { id: 'symbol-1', node_type: 'Function', repository_id: 'repository-1', snapshot_id: 'snapshot-1', file_path: 'main.py', qualified_name: 'main.main' },
  ],
  relationships: [
    { id: 'contains-1', relationship_type: 'CONTAINS', source_id: 'snapshot-1', target_id: 'file-1', repository_id: 'repository-1', snapshot_id: 'snapshot-1' },
    { id: 'declares-1', relationship_type: 'DECLARES', source_id: 'file-1', target_id: 'symbol-1', repository_id: 'repository-1', snapshot_id: 'snapshot-1' },
  ],
}

function pipelineOperation() {
  const analysisStarted = vi.mocked(analyzeSnapshot).mock.calls.length > 0
  const graphStarted = vi.mocked(persistGraph).mock.calls.length > 0
  const vectorStarted = vi.mocked(buildVectorIndex).mock.calls.length > 0
  const stages = {
    ingestion: 'complete',
    analysis: graphStarted || vectorStarted ? 'complete' : analysisStarted ? 'running' : 'pending',
    graph: vectorStarted ? 'complete' : graphStarted ? 'running' : 'pending',
    vector: vectorStarted ? 'complete' : 'pending',
  }
  const events = [operationEvent('ingestion-1', 'ingestion', 'done', 'Persisting immutable snapshot metadata')]
  if (analysisStarted) events.push(operationEvent('analysis-1', 'analysis', graphStarted ? 'done' : 'running', 'Parsing Python ASTs and extracting structural records', { key: 'symbols', label: 'Symbols', value: 2 }))
  if (graphStarted) events.push(operationEvent('graph-1', 'graph', vectorStarted ? 'done' : 'running', 'Persisting repository-scoped code graph', { key: 'nodes', label: 'Nodes', value: 11 }))
  if (vectorStarted) events.push(operationEvent('vector-1', 'vector', 'done', 'Constructing and persisting FAISS index artifacts', { key: 'chunks', label: 'Chunks', value: 5 }))
  return { operation_id: 'operation-1', status: vectorStarted ? 'complete' : 'running', stages, events, metrics: {}, created_at: '2026-08-25T00:00:00Z', updated_at: '2026-08-25T00:00:04Z' }
}

function operationEvent(id, stage, status, message, metric = null) {
  return { id, sequence: Number(id.at(-1)), stage, status, message, started_at: '2026-08-25T00:00:00Z', completed_at: status === 'running' ? null : '2026-08-25T00:00:01Z', metric }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, reject, resolve }
}

async function registerAndAnalyze() {
  fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
  fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))
  const analyzeButton = await screen.findByRole('button', { name: 'Run pipeline' })
  fireEvent.click(analyzeButton)
  await screen.findByRole('button', { name: 'Pipeline complete' })
}

describe('App', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.removeAttribute('data-theme-preference')
    vi.mocked(getHealth).mockResolvedValue({ status: 'healthy', application: 'CodeGraph AI', version: '0.1.0' })
    vi.mocked(getReadiness).mockResolvedValue({ status: 'ready', dependencies: { mongodb: { status: 'ready' }, neo4j: { status: 'ready' } } })
    vi.mocked(registerRepository).mockResolvedValue(registration)
    vi.mocked(analyzeSnapshot).mockResolvedValue({ snapshot_id: 'snapshot-1', symbols: [{ id: 'file-1', symbol_type: 'file' }, { id: 'symbol-1', symbol_type: 'function' }], imports: [{ id: 'import-1' }], inheritances: [], calls: [{ id: 'call-1', resolution: 'resolved' }], diagnostics: [] })
    vi.mocked(persistGraph).mockResolvedValue({ repository_id: 'repository-1', snapshot_id: 'snapshot-1', status: 'persisted', node_count: 11, relationship_count: 9, idempotent: false, diagnostic_count: 0 })
    vi.mocked(buildVectorIndex).mockResolvedValue({ repository_id: 'repository-1', snapshot_id: 'snapshot-1', status: 'ready', index_id: 'index-1', chunk_count: 5, vector_dimension: 32 })
    vi.mocked(getPipelineOperation).mockImplementation(async () => pipelineOperation())
    vi.mocked(getGraphPreview).mockResolvedValue(graphPreview)
  })

  it('registers a repository and renders immutable repository metadata', async () => {
    render(<App />)
    expect(screen.queryByRole('link', { name: 'View on GitHub' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))

    expect(await screen.findByRole('heading', { name: 'octocat / hello-python' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { name: 'Pipeline Progress' })).toBeInTheDocument()
    const operationPanel = screen.getByRole('heading', { name: 'Pipeline Progress' }).closest('.pipeline-operation-panel')
    expect(operationPanel).toContainElement(screen.getByLabelText('Live Backend Activity'))
    expect(screen.getByText(registration.snapshot.commit_sha.slice(0, 7))).toBeInTheDocument()
    expect(screen.getAllByText('snapshot-1').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('7').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Copy snapshot ID' })).toBeInTheDocument()
    const githubLink = screen.getByRole('link', { name: 'View on GitHub' })
    expect(githubLink).toHaveAttribute('href', registration.repository.github_url)
    expect(githubLink.closest('.top-bar__repository-actions')).toContainElement(screen.getByRole('group', { name: 'Theme preference' }))
    expect(registerRepository).toHaveBeenCalledWith(registration.repository.github_url, expect.any(String))
  })

  it('validates GitHub repository URLs before registration', () => {
    vi.mocked(getHealth).mockReturnValue(new Promise(() => {}))
    vi.mocked(getReadiness).mockReturnValue(new Promise(() => {}))
    render(<App />)
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: 'github.com/not-complete' } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Enter a complete public GitHub repository URL.')
    expect(registerRepository).not.toHaveBeenCalled()
  })

  it('shows an accessible repository connection state while registration is active', async () => {
    vi.mocked(registerRepository).mockReturnValue(new Promise(() => {}))
    render(<App />)
    await screen.findByText('API connected')
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))

    const activity = await screen.findByRole('status', { name: 'Live Backend Activity' })
    expect(activity).toHaveTextContent('Persisting immutable snapshot metadata')
    expect(screen.getByRole('button', { name: /Connecting source/ })).toBeDisabled()
  })

  it('retires a stale operation and stops polling after the backend returns 404', async () => {
    vi.mocked(registerRepository).mockReturnValue(new Promise(() => {}))
    vi.mocked(getPipelineOperation).mockRejectedValue(Object.assign(new Error('Pipeline operation was not found'), { status: 404 }))
    render(<App />)
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))

    expect(await screen.findByText('Live activity ended because the backend operation is no longer available.')).toBeInTheDocument()
    expect(getPipelineOperation).toHaveBeenCalledTimes(1)
    await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 750)) })
    expect(getPipelineOperation).toHaveBeenCalledTimes(1)
  })

  it('runs every processing stage and renders pipeline metrics', async () => {
    render(<App />)
    await registerAndAnalyze()

    const pipeline = screen.getAllByRole('list', { name: 'Repository processing pipeline' })[0]
    expect(within(pipeline).getAllByText('Complete')).toHaveLength(4)
    expect(screen.getByRole('heading', { name: 'Artifacts' })).toBeInTheDocument()
    expect(screen.getByText('Structural Analysis')).toBeInTheDocument()
    expect(screen.getByText('Code Graph')).toBeInTheDocument()
    expect(screen.getByText('Semantic Index')).toBeInTheDocument()
    expect(analyzeSnapshot).toHaveBeenCalledWith('repository-1', 'snapshot-1', expect.any(String))
    expect(persistGraph).toHaveBeenCalledWith('repository-1', 'snapshot-1', expect.any(String))
    expect(buildVectorIndex).toHaveBeenCalledWith('repository-1', 'snapshot-1', expect.any(String))
  })

  it('uses stage-specific Processing Activity throughout the repository pipeline', async () => {
    const registrationRequest = deferred()
    const analysisRequest = deferred()
    const graphRequest = deferred()
    const vectorRequest = deferred()
    vi.mocked(registerRepository).mockReturnValue(registrationRequest.promise)
    vi.mocked(analyzeSnapshot).mockReturnValue(analysisRequest.promise)
    vi.mocked(persistGraph).mockReturnValue(graphRequest.promise)
    vi.mocked(buildVectorIndex).mockReturnValue(vectorRequest.promise)
    render(<App />)
    await act(async () => {})
    expect(screen.getByText('API connected')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))

    expect(await screen.findByRole('status', { name: 'Live Backend Activity' })).toHaveTextContent('Persisting immutable snapshot metadata')
    await act(async () => {
      registrationRequest.resolve(registration)
      await registrationRequest.promise
    })
    fireEvent.click(screen.getByRole('button', { name: 'Run pipeline' }))

    expect(await screen.findByRole('status', { name: 'Live Backend Activity' })).toHaveTextContent('Parsing Python ASTs and extracting structural records')
    expect(screen.queryByText(/% complete/i)).not.toBeInTheDocument()

    await act(async () => {
      analysisRequest.resolve({ snapshot_id: 'snapshot-1', symbols: [], imports: [], inheritances: [], calls: [], diagnostics: [] })
      await analysisRequest.promise
    })
    await waitFor(() => expect(screen.getByRole('status', { name: 'Live Backend Activity' })).toHaveTextContent('Persisting repository-scoped code graph'))

    await act(async () => {
      graphRequest.resolve({ node_count: 11, relationship_count: 9 })
      await graphRequest.promise
    })
    await waitFor(() => expect(screen.getByRole('region', { name: 'Live Backend Activity' })).toHaveTextContent('Constructing and persisting FAISS index artifacts'))

    await act(async () => {
      vectorRequest.resolve({ chunk_count: 5 })
      await vectorRequest.promise
    })
    expect(screen.getByRole('button', { name: 'Pipeline complete' })).toBeDisabled()
    expect(screen.getByRole('region', { name: 'Live Backend Activity' })).toHaveTextContent('Complete')
    expect(screen.getAllByText('Complete').length).toBeGreaterThanOrEqual(7)
  })

  it('renders a grounded Q&A response with authoritative source evidence', async () => {
    vi.mocked(askRepository).mockResolvedValue(answeredQuery)
    render(<App />)
    await registerAndAnalyze()
    fireEvent.click(screen.getByRole('button', { name: /^Intelligence/ }))
    fireEvent.change(screen.getByLabelText('Query repository'), { target: { value: 'How is ingestion bounded?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Run query' }))

    expect(await screen.findByText('Archives are checked against configured extraction limits.')).toBeInTheDocument()
    const explorer = screen.getByRole('region', { name: 'Evidence explorer' })
    expect(within(explorer).getAllByText('backend/app/modules/ingestion/archive.py')).toHaveLength(2)
    expect(within(explorer).getAllByText(/SafeZipExtractor\.extract/)).toHaveLength(2)
    expect(within(explorer).getByText('42–43')).toBeInTheDocument()
    expect(within(explorer).getByText('42')).toBeInTheDocument()
    expect(screen.getByText('Only the selected ingestion path was inspected.')).toBeInTheDocument()

    fireEvent.click(within(explorer).getByRole('button', { name: /backend\/app\/core\/config\.py/ }))
    expect(within(explorer).getAllByText('backend/app/core/config.py')).toHaveLength(2)
    expect(within(explorer).getByText('10–12')).toBeInTheDocument()
    expect(within(explorer).getByText('max_archive_bytes = 100_000')).toBeInTheDocument()
  })

  it('replaces query Processing Activity with the grounded result when the request completes', async () => {
    const queryRequest = deferred()
    vi.mocked(askRepository).mockReturnValue(queryRequest.promise)
    render(<App />)
    await registerAndAnalyze()
    fireEvent.click(screen.getByRole('button', { name: /^Intelligence/ }))
    fireEvent.change(screen.getByLabelText('Query repository'), { target: { value: 'How is ingestion bounded?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Run query' }))

    const activity = screen.getByRole('status', { name: 'Processing Activity — Repository Q&A' })
    expect(activity).toHaveTextContent('Searching semantic code evidence')
    expect(activity).toHaveTextContent('Validating structured output with Pydantic')
    expect(activity).toHaveTextContent('Validating supplied evidence citations')
    expect(screen.getByText('Evidence explorer')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retrieving/ })).toBeDisabled()

    await act(async () => {
      queryRequest.resolve(answeredQuery)
      await queryRequest.promise
    })
    expect(screen.getByText(answeredQuery.answer)).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Processing Activity — Repository Q&A' })).not.toBeInTheDocument()
  })

  it('selects a curated Intelligence placeholder and keeps it stable across rerenders', async () => {
    render(<App />)
    await registerAndAnalyze()
    fireEvent.click(screen.getByRole('button', { name: /^Intelligence/ }))
    const queryInput = screen.getByLabelText('Query repository')
    const placeholder = queryInput.getAttribute('placeholder')

    expect(INTELLIGENCE_QUESTIONS).toContain(placeholder)
    fireEvent.change(queryInput, { target: { value: 'temporary input' } })
    expect(queryInput).toHaveAttribute('placeholder', placeholder)
    fireEvent.click(screen.getByRole('button', { name: /^System/ }))
    fireEvent.click(screen.getByRole('button', { name: /^Intelligence/ }))
    expect(screen.getByLabelText('Query repository')).toHaveAttribute('placeholder', placeholder)
  })

  it('submits a non-empty Intelligence query with Enter', async () => {
    vi.mocked(askRepository).mockReturnValue(new Promise(() => {}))
    render(<App />)
    await registerAndAnalyze()
    fireEvent.click(screen.getByRole('button', { name: /^Intelligence/ }))
    const queryInput = screen.getByLabelText('Query repository')
    fireEvent.change(queryInput, { target: { value: 'Where is validation implemented?' } })
    fireEvent.keyDown(queryInput, { key: 'Enter' })

    expect(askRepository).toHaveBeenCalledWith('repository-1', 'snapshot-1', 'Where is validation implemented?')
  })

  it('keeps Shift+Enter for newlines and ignores empty Enter submissions', async () => {
    render(<App />)
    await registerAndAnalyze()
    fireEvent.click(screen.getByRole('button', { name: /^Intelligence/ }))
    const queryInput = screen.getByLabelText('Query repository')

    fireEvent.keyDown(queryInput, { key: 'Enter' })
    fireEvent.change(queryInput, { target: { value: 'First line' } })
    fireEvent.keyDown(queryInput, { key: 'Enter', shiftKey: true })
    expect(askRepository).not.toHaveBeenCalled()
  })

  it('does not duplicate an Enter submission while a query is loading', async () => {
    vi.mocked(askRepository).mockReturnValue(new Promise(() => {}))
    render(<App />)
    await registerAndAnalyze()
    fireEvent.click(screen.getByRole('button', { name: /^Intelligence/ }))
    const queryInput = screen.getByLabelText('Query repository')
    fireEvent.change(queryInput, { target: { value: 'Trace the request lifecycle.' } })
    fireEvent.keyDown(queryInput, { key: 'Enter' })
    fireEvent.keyDown(queryInput, { key: 'Enter' })

    expect(askRepository).toHaveBeenCalledTimes(1)
  })

  it('copies evidence source and file paths with confirmation feedback', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    vi.mocked(askRepository).mockResolvedValue(answeredQuery)
    render(<App />)
    await registerAndAnalyze()
    fireEvent.click(screen.getByRole('button', { name: /^Intelligence/ }))
    fireEvent.change(screen.getByLabelText('Query repository'), { target: { value: 'How is ingestion bounded?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Run query' }))

    await screen.findByText(answeredQuery.answer)
    fireEvent.click(screen.getByRole('button', { name: 'Copy file path' }))
    fireEvent.click(screen.getByRole('button', { name: 'Copy source excerpt' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2))
    expect(screen.getAllByText('Copied')).toHaveLength(2)
  })

  it('shows the explicit insufficient-evidence state without an answer panel', async () => {
    vi.mocked(askRepository).mockResolvedValue({ outcome: 'insufficient_evidence', answer: '', cited_evidence_ids: [], evidence: [], limitations: [], retrieval_metadata: {} })
    render(<App />)
    await registerAndAnalyze()
    fireEvent.click(screen.getByRole('button', { name: /^Intelligence/ }))
    fireEvent.change(screen.getByLabelText('Query repository'), { target: { value: 'Where is the payment gateway?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Run query' }))

    expect(await screen.findByText('Insufficient repository evidence was retrieved for this query.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Response' })).not.toBeInTheDocument()
  })

  it('renders only measured structural, graph, and vector metrics', async () => {
    render(<App />)
    await registerAndAnalyze()

    const preview = screen.getByRole('region', { name: 'Live Visual Preview' })
    expect(preview).toHaveTextContent('Python files1')
    expect(preview).toHaveTextContent('Functions1')
    expect(preview).toHaveTextContent('Total Nodes11')
    expect(preview).toHaveTextContent('Total Relationships9')
    expect(preview).toHaveTextContent('Semantic chunks5')
    expect(preview).toHaveTextContent('Vector dimensions32')
    expect(preview).not.toHaveTextContent('%')
  })

  it('renders a bounded graph preview from persisted backend nodes and edges', async () => {
    render(<App />)
    await registerAndAnalyze()

    const preview = screen.getByRole('region', { name: 'Graph Structure Preview' })
    expect(within(preview).getByRole('img', { name: 'Persisted graph preview with 3 nodes and 2 relationships' })).toBeInTheDocument()
    expect(preview).toHaveTextContent('Snapshot')
    expect(preview).toHaveTextContent('File')
    expect(preview).toHaveTextContent('Function')
    expect(preview).toHaveTextContent('CONTAINS1')
    expect(preview).toHaveTextContent('DECLARES1')
    expect(getGraphPreview).toHaveBeenCalledWith('repository-1', 'snapshot-1')
  })

  it('uses segmented connectors around markers in horizontal and vertical pipelines', async () => {
    render(<App />)
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))
    await screen.findByRole('heading', { name: 'Pipeline Progress' })

    const [horizontal, vertical] = screen.getAllByRole('list', { name: 'Repository processing pipeline' })
    expect(horizontal).toHaveAttribute('data-orientation', 'horizontal')
    expect(vertical).toHaveAttribute('data-orientation', 'vertical')
    for (const pipeline of [horizontal, vertical]) {
      const stages = within(pipeline).getAllByRole('listitem')
      expect(stages).toHaveLength(4)
      stages.forEach((stage) => {
        const track = stage.querySelector('.pipeline__track')
        const marker = stage.querySelector('.pipeline__index')
        expect(track?.querySelectorAll('.pipeline__connector')).toHaveLength(2)
        expect(marker?.querySelector('.pipeline__connector')).toBeNull()
      })
    }
  })

  it('keeps graph preview indeterminate until persisted data exists', async () => {
    const graphRequest = deferred()
    vi.mocked(persistGraph).mockReturnValue(graphRequest.promise)
    render(<App />)
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Run pipeline' }))

    const previewState = await screen.findByText('Persisting graph structure')
    const preview = previewState.closest('section')
    expect(preview).not.toHaveTextContent(/nodes ·/)
    expect(screen.getByRole('region', { name: 'Live Visual Preview' })).not.toHaveTextContent('Total Nodes')
  })

  it('renders an honest empty graph state before graph persistence', async () => {
    render(<App />)
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))

    expect(await screen.findByText('No persisted graph yet')).toBeInTheDocument()
    expect(screen.getByText('No graph metrics yet')).toBeInTheDocument()
    expect(screen.queryByText(/0 nodes · 0 edges/)).not.toBeInTheDocument()
  })

  it('supports graph selection details and expanded inspection using real preview data', async () => {
    render(<App />)
    await registerAndAnalyze()

    const graph = screen.getByRole('region', { name: 'Graph Structure Preview' })
    fireEvent.mouseEnter(within(graph).getByRole('button', { name: 'main.py' }))
    expect(graph).toHaveTextContent('2 visible relationships')
    fireEvent.click(within(graph).getByRole('button', { name: 'Expand' }))
    expect(screen.getByRole('dialog', { name: 'Expanded Graph Structure Preview' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close expanded graph' }))
    expect(screen.queryByRole('dialog', { name: 'Expanded Graph Structure Preview' })).not.toBeInTheDocument()
  })

  it('enables View Intelligence only after the real pipeline is ready', async () => {
    render(<App />)
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))

    expect(await screen.findByRole('button', { name: 'View Intelligence' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Run pipeline' }))
    expect(await screen.findByRole('button', { name: 'Pipeline complete' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'View Intelligence' })).toBeEnabled()
  })

  it('marks the actual failing stage without advancing later stages', async () => {
    vi.mocked(persistGraph).mockRejectedValue(new Error('Neo4j graph operation failed'))
    render(<App />)
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Run pipeline' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Graph indexing failed')
    const pipeline = screen.getAllByRole('list', { name: 'Repository processing pipeline' })[0]
    expect(within(pipeline).getByText('Code graph').closest('li')).toHaveClass('pipeline__stage--failed')
    expect(within(pipeline).getByText('Semantic index').closest('li')).toHaveClass('pipeline__stage--pending')
  })

  it('renders repository and API errors without exposing implementation details', async () => {
    vi.mocked(registerRepository).mockRejectedValue(new Error('Repository could not be found or is not public.'))
    render(<App />)
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Repository unavailable')
    expect(alert).toHaveTextContent('Repository could not be found or is not public.')
  })

  it('renders backend, MongoDB, and Neo4j health independently', async () => {
    vi.mocked(getReadiness).mockResolvedValue({ status: 'not_ready', dependencies: { mongodb: { status: 'ready' }, neo4j: { status: 'unavailable' } } })
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: /^System/ }))

    expect(await screen.findByText('CodeGraph AI v0.1.0')).toBeInTheDocument()
    const rows = within(screen.getByRole('table')).getAllByText(/Available|Unavailable/)
    expect(rows).toHaveLength(3)
    expect(screen.getByText('MongoDB')).toBeInTheDocument()
    expect(screen.getByText('Neo4j')).toBeInTheDocument()
    expect(screen.getByText('Unavailable')).toBeInTheDocument()
  })

  it('refreshes all system checks from a single accessible action', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: /^System/ }))
    const refreshButton = await screen.findByRole('button', { name: 'Refresh status' })
    fireEvent.click(refreshButton)

    await waitFor(() => expect(getHealth).toHaveBeenCalledTimes(2))
    expect(getReadiness).toHaveBeenCalledTimes(2)
  })

  it('defaults to system and persists light, dark, and system theme preferences', async () => {
    const firstRender = render(<App />)
    await screen.findByText('API connected')
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(document.documentElement).toHaveAttribute('data-theme-preference', 'system')
    expect(window.localStorage.getItem('codegraph-theme')).toBe('system')
    expect(screen.getByRole('button', { name: 'system theme' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: 'light theme' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(window.localStorage.getItem('codegraph-theme')).toBe('light')

    firstRender.unmount()
    render(<App />)
    await screen.findByText('API connected')
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(screen.getByRole('button', { name: 'light theme' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: 'dark theme' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')

    fireEvent.click(screen.getByRole('button', { name: 'system theme' }))
    expect(document.documentElement).toHaveAttribute('data-theme-preference', 'system')
    expect(window.localStorage.getItem('codegraph-theme')).toBe('system')
  })

  it('renders completed, active, and pending pipeline states from the actual workflow', async () => {
    const analysisRequest = deferred()
    vi.mocked(analyzeSnapshot).mockReturnValue(analysisRequest.promise)
    render(<App />)
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Run pipeline' }))

    const pipeline = screen.getAllByRole('list', { name: 'Repository processing pipeline' })[0]
    expect(within(pipeline).getByText('Repository ingestion').closest('li')).toHaveClass('pipeline__stage--complete')
    expect(within(pipeline).getByText('Structural analysis').closest('li')).toHaveClass('pipeline__stage--running')
    expect(within(pipeline).getByText('Code graph').closest('li')).toHaveClass('pipeline__stage--pending')

    await act(async () => analysisRequest.reject(new Error('Stop the intentionally suspended pipeline.')))
    await screen.findByRole('alert')
  })
})
