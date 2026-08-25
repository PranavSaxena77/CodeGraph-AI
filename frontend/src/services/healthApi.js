import { apiRequest } from './apiClient.js'

export async function getHealth() {
  return apiRequest('/health')
}

export async function getReadiness() {
  return apiRequest('/ready', {}, [503])
}
