import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.jsx'
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

async function registerAndAnalyze() {
  fireEvent.change(screen.getByLabelText('GitHub repository URL'), { target: { value: registration.repository.github_url } })
  fireEvent.click(screen.getByRole('button', { name: 'Register repository' }))
  const analyzeButton = await screen.findByRole('button', { name: 'Run analysis' })
  fireEvent.click(analyzeButton)
  await screen.findByRole('button', { name: 'Analysis complete' })
}

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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

    expect(await screen.findByText('Repository overview')).toBeInTheDocument()
    expect(screen.getAllByText('octocat/hello-python').length).toBeGreaterThan(0)
    expect(screen.getByText(registration.snapshot.commit_sha)).toBeInTheDocument()
    expect(screen.getAllByText('snapshot-1')).toHaveLength(2)
    expect(screen.getByText('7')).toBeInTheDocument()
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

  it('runs every processing stage and renders pipeline metrics', async () => {
    render(<App />)
    await registerAndAnalyze()

    const pipeline = screen.getByRole('list', { name: 'Repository processing pipeline' })
    expect(within(pipeline).getAllByText('COMPLETE')).toHaveLength(5)
    const summary = screen.getByLabelText('Analysis summary')
    expect(within(summary).getByText('2')).toBeInTheDocument()
    expect(within(summary).getByText('11')).toBeInTheDocument()
    expect(within(summary).getByText('9')).toBeInTheDocument()
    expect(within(summary).getByText('5')).toBeInTheDocument()
    expect(analyzeSnapshot).toHaveBeenCalledWith('repository-1', 'snapshot-1')
    expect(persistGraph).toHaveBeenCalledWith('repository-1', 'snapshot-1')
    expect(buildVectorIndex).toHaveBeenCalledWith('repository-1', 'snapshot-1')
  })

  it('renders a grounded Q&A response with authoritative source evidence', async () => {
    vi.mocked(askRepository).mockResolvedValue({
      repository_id: 'repository-1', snapshot_id: 'snapshot-1', commit_sha: registration.snapshot.commit_sha,
      question: 'How is ingestion bounded?', outcome: 'answered', answer: 'Archives are checked against configured extraction limits.',
      cited_evidence_ids: ['E1'], limitations: ['Only the selected ingestion path was inspected.'],
      evidence: [
        { evidence_id: 'E1', chunk_id: 'chunk-1', repository_id: 'repository-1', snapshot_id: 'snapshot-1', commit_sha: registration.snapshot.commit_sha, file_path: 'backend/app/modules/ingestion/archive.py', symbol_id: 'symbol-1', symbol_name: 'extract', qualified_name: 'SafeZipExtractor.extract', symbol_type: 'method', start_line: 42, end_line: 43, content: 'def extract(self, archive):\n    self._validate_limits(archive)' },
        { evidence_id: 'E2', chunk_id: 'chunk-2', repository_id: 'repository-1', snapshot_id: 'snapshot-1', commit_sha: registration.snapshot.commit_sha, file_path: 'backend/app/core/config.py', symbol_id: 'symbol-2', symbol_name: 'Settings', qualified_name: 'Settings', symbol_type: 'class', start_line: 10, end_line: 12, content: 'class Settings:\n    max_archive_bytes = 100_000\n    max_file_bytes = 10_000' },
      ],
      retrieval_metadata: {},
    })
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
    const rows = screen.getAllByText(/Available|Unavailable/)
    expect(rows).toHaveLength(3)
    expect(screen.getByText('MongoDB')).toBeInTheDocument()
    expect(screen.getByText('Neo4j')).toBeInTheDocument()
    expect(screen.getByText('Unavailable')).toBeInTheDocument()
  })
})
