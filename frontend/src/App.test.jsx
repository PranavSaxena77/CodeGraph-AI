import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.jsx'
import { getHealth, getReadiness } from './services/healthApi.js'

vi.mock('./services/healthApi.js', () => ({
  getHealth: vi.fn(),
  getReadiness: vi.fn(),
}))

describe('App', () => {
  beforeEach(() => {
    vi.mocked(getHealth).mockResolvedValue({
      status: 'healthy',
      application: 'CodeGraph AI',
      version: '0.1.0',
    })
    vi.mocked(getReadiness).mockResolvedValue({
      status: 'ready',
      dependencies: {
        mongodb: { status: 'ready' },
        neo4j: { status: 'ready' },
      },
    })
  })

  it('shows backend health and dependency readiness', async () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { name: /understand code through structure/i }),
    ).toBeInTheDocument()
    expect(await screen.findByText('Healthy')).toBeInTheDocument()
    expect(await screen.findByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('CodeGraph AI v0.1.0')).toBeInTheDocument()
  })
})
