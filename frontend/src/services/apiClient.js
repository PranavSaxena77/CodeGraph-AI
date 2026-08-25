const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

const DEFAULT_ERROR_MESSAGE = 'The request could not be completed.'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function parseBody(response) {
  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) return null
  try {
    return await response.json()
  } catch {
    return null
  }
}

export async function apiRequest(path, options = {}, acceptedStatuses = []) {
  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
  } catch {
    throw new ApiError('The backend is unavailable. Check that the API is running.', 0)
  }

  const body = await parseBody(response)
  if (!response.ok && !acceptedStatuses.includes(response.status)) {
    const detail = typeof body?.detail === 'string' ? body.detail : DEFAULT_ERROR_MESSAGE
    throw new ApiError(detail, response.status)
  }
  return body
}
