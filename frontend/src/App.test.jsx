import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.jsx'
import { INTELLIGENCE_QUESTIONS } from './components/intelligenceQuestions.js'
import { getHealth, getReadiness } from './services/healthApi.js'
import { analyzeSnapshot, askRepository, buildVectorIndex, persistGraph, registerRepository } from './services/repositoryApi.js'

vi.mock('./services/healthApi.js', () => ({ getHealth: vi.fn(), getReadiness: vi.fn() }))
vi.mock('./services/repositoryApi.js', () => ({
  registerRepository: vi.fn(),
  analyzeSnapshot: vi.fn(),
  persistGraph: vi.fn(),
  buildVectorIndex: vi.fn(),
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
    vi.mocked(getHealth).mockResolvedValue({ status: 'healthy', application: 'CodeGraph AI', version: '0.1.0' })
    vi.mocked(getReadiness).mockResolvedValue({ status: 'ready', dependencies: { mongodb: { status: 'ready' }, neo4j: { status: 'ready' } } })
    vi.mocked(registerRepository).mockResolvedValue(registration)
    vi.mocked(analyzeSnapshot).mockResolvedValue({ snapshot_id: 'snapshot-1', symbols: [{ id: 'symbol-1' }, { id: 'symbol-2' }], imports: [], inheritances: [], calls: [], diagnostics: [] })
    vi.mocked(persistGraph).mockResolvedValue({ repository_id: 'repository-1', snapshot_id: 'snapshot-1', status: 'persisted', node_count: 11, relationship_count: 9, idempotent: false, diagnostic_count: 0 })
    vi.mocked(buildVectorIndex).mockResolvedValue({ repository_id: 'repository-1', snapshot_id: 'snapshot-1', status: 'ready', index_id: 'index-1', chunk_count: 5, vector_dimension: 32 })
  })

  it('registers a repository and renders immutable repository metadata', async () => {
    render(<App />)
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))

    expect(await screen.findByRole('heading', { name: 'octocat / hello-python' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { name: 'Repository Details' })).toBeInTheDocument()
    expect(screen.getByText(registration.snapshot.commit_sha)).toBeInTheDocument()
    expect(screen.getAllByText('snapshot-1')).toHaveLength(2)
    expect(screen.getAllByText('7').length).toBeGreaterThan(0)
    expect(registerRepository).toHaveBeenCalledWith(registration.repository.github_url)
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

    const activity = screen.getByRole('status', { name: 'Processing Activity — Repository ingestion' })
    expect(activity).toHaveTextContent('Resolving GitHub repository metadata')
    expect(activity).toHaveTextContent('Persisting repository snapshot metadata')
    expect(screen.getByRole('button', { name: /Connecting source/ })).toBeDisabled()
  })

  it('runs every processing stage and renders pipeline metrics', async () => {
    render(<App />)
    await registerAndAnalyze()

    const pipeline = screen.getByRole('list', { name: 'Repository processing pipeline' })
    expect(within(pipeline).getAllByText('COMPLETE')).toHaveLength(4)
    expect(screen.getByRole('heading', { name: 'Artifacts' })).toBeInTheDocument()
    expect(screen.getByText('Structural Analysis')).toBeInTheDocument()
    expect(screen.getByText('Code Graph')).toBeInTheDocument()
    expect(screen.getByText('Semantic Index')).toBeInTheDocument()
    expect(analyzeSnapshot).toHaveBeenCalledWith('repository-1', 'snapshot-1')
    expect(persistGraph).toHaveBeenCalledWith('repository-1', 'snapshot-1')
    expect(buildVectorIndex).toHaveBeenCalledWith('repository-1', 'snapshot-1')
  })

  it('uses stage-specific Processing Activity throughout the repository pipeline', async () => {
    vi.useFakeTimers()
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

    expect(screen.getByRole('status', { name: 'Processing Activity — Repository ingestion' })).toHaveTextContent('Downloading repository archive')
    await act(async () => {
      registrationRequest.resolve(registration)
      await registrationRequest.promise
    })
    fireEvent.click(screen.getByRole('button', { name: 'Run pipeline' }))

    expect(screen.getByRole('status', { name: 'Processing Activity' })).toHaveTextContent('Parsing Python syntax trees')
    expect(screen.queryByText(/% complete/i)).not.toBeInTheDocument()

    await act(async () => {
      analysisRequest.resolve({ snapshot_id: 'snapshot-1', symbols: [], imports: [], inheritances: [], calls: [], diagnostics: [] })
      await analysisRequest.promise
    })
    expect(screen.getByRole('status', { name: 'Processing Activity' })).toHaveTextContent('Persisting DECLARES and CONTAINS relationships')

    await act(async () => {
      graphRequest.resolve({ node_count: 11, relationship_count: 9 })
      await graphRequest.promise
    })
    expect(screen.getByRole('status', { name: 'Processing Activity' })).toHaveTextContent('Building FAISS index')

    await act(async () => {
      vectorRequest.resolve({ chunk_count: 5 })
      await vectorRequest.promise
    })
    expect(screen.getByRole('button', { name: 'Pipeline complete' })).toBeDisabled()
    expect(screen.queryByRole('status', { name: /Processing Activity/ })).not.toBeInTheDocument()
    expect(screen.getAllByText('COMPLETE').length).toBeGreaterThanOrEqual(7)
    vi.useRealTimers()
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
    const rows = screen.getAllByText(/AVAILABLE|UNAVAILABLE/)
    expect(rows).toHaveLength(3)
    expect(screen.getByText('MongoDB')).toBeInTheDocument()
    expect(screen.getByText('Neo4j')).toBeInTheDocument()
    expect(screen.getByText('UNAVAILABLE')).toBeInTheDocument()
  })

  it('refreshes all system checks from a single accessible action', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: /^System/ }))
    const refreshButton = await screen.findByRole('button', { name: 'Refresh status' })
    fireEvent.click(refreshButton)

    await waitFor(() => expect(getHealth).toHaveBeenCalledTimes(2))
    expect(getReadiness).toHaveBeenCalledTimes(2)
  })

  it('applies and persists light and dark themes', async () => {
    const firstRender = render(<App />)
    await screen.findByText('API connected')
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')

    fireEvent.click(screen.getByRole('button', { name: 'light' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(window.localStorage.getItem('codegraph-theme')).toBe('light')

    firstRender.unmount()
    render(<App />)
    await screen.findByText('API connected')
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(screen.getByRole('button', { name: 'light' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: 'dark' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
  })

  it('renders completed, active, and pending pipeline states from the actual workflow', async () => {
    const analysisRequest = deferred()
    vi.mocked(analyzeSnapshot).mockReturnValue(analysisRequest.promise)
    render(<App />)
    fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Run pipeline' }))

    const pipeline = screen.getByRole('list', { name: 'Repository processing pipeline' })
    expect(within(pipeline).getByText('Repository ingestion').closest('li')).toHaveClass('pipeline__stage--complete')
    expect(within(pipeline).getByText('Structural analysis').closest('li')).toHaveClass('pipeline__stage--running')
    expect(within(pipeline).getByText('Code graph').closest('li')).toHaveClass('pipeline__stage--pending')
  })
})
