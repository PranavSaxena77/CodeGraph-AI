const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

async function readJson(response) {
  const body = await response.json()
  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`)
  }
  return body
}

export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/health`)
  return readJson(response)
}

export async function getReadiness() {
  const response = await fetch(`${API_BASE_URL}/ready`)
  const body = await response.json()
  if (response.ok || response.status === 503) {
    return body
  }
  throw new Error(`API request failed with status ${response.status}`)
}
