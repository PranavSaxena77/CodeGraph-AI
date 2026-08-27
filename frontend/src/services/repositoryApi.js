import { apiRequest } from './apiClient.js'

function snapshotPath(repositoryId, snapshotId, suffix = '') {
  return `/repositories/${encodeURIComponent(repositoryId)}/snapshots/${encodeURIComponent(snapshotId)}${suffix}`
}

function operationOptions(operationId) {
  return operationId ? { 'X-CodeGraph-Operation-ID': operationId } : {}
}

export function registerRepository(githubUrl, operationId) {
  return apiRequest('/repositories', {
    method: 'POST',
    headers: operationOptions(operationId),
    body: JSON.stringify({ github_url: githubUrl }),
  })
}

export function analyzeSnapshot(repositoryId, snapshotId, operationId) {
  return apiRequest(snapshotPath(repositoryId, snapshotId, '/analysis'), { method: 'POST', headers: operationOptions(operationId) })
}

export function persistGraph(repositoryId, snapshotId, operationId) {
  return apiRequest(snapshotPath(repositoryId, snapshotId, '/graph'), { method: 'POST', headers: operationOptions(operationId) })
}

export function buildVectorIndex(repositoryId, snapshotId, operationId) {
  return apiRequest(snapshotPath(repositoryId, snapshotId, '/vector-index'), { method: 'POST', headers: operationOptions(operationId) })
}

export function getPipelineOperation(operationId) {
  return apiRequest(`/operations/${encodeURIComponent(operationId)}`)
}

export function getGraphPreview(repositoryId, snapshotId, maxNodes = 60) {
  return apiRequest(`${snapshotPath(repositoryId, snapshotId, '/graph-preview')}?max_nodes=${maxNodes}`)
}

export function askRepository(repositoryId, snapshotId, question) {
  return apiRequest(snapshotPath(repositoryId, snapshotId, '/ask'), {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}
