import { apiRequest } from './apiClient.js'

function snapshotPath(repositoryId, snapshotId, suffix = '') {
  return `/repositories/${encodeURIComponent(repositoryId)}/snapshots/${encodeURIComponent(snapshotId)}${suffix}`
}

export function registerRepository(githubUrl) {
  return apiRequest('/repositories', {
    method: 'POST',
    body: JSON.stringify({ github_url: githubUrl }),
  })
}

export function analyzeSnapshot(repositoryId, snapshotId) {
  return apiRequest(snapshotPath(repositoryId, snapshotId, '/analysis'), { method: 'POST' })
}

export function persistGraph(repositoryId, snapshotId) {
  return apiRequest(snapshotPath(repositoryId, snapshotId, '/graph'), { method: 'POST' })
}

export function buildVectorIndex(repositoryId, snapshotId) {
  return apiRequest(snapshotPath(repositoryId, snapshotId, '/vector-index'), { method: 'POST' })
}

export function askRepository(repositoryId, snapshotId, question) {
  return apiRequest(snapshotPath(repositoryId, snapshotId, '/ask'), {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}
