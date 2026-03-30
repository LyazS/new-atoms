const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

if (!API_BASE_URL) {
  throw new Error('Missing VITE_API_BASE_URL. Please configure the frontend environment file.')
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function getApiBaseUrl() {
  return API_BASE_URL
}

export async function apiFetch(path: string, init: RequestInit = {}, token?: string | null) {
  const headers = new Headers(init.headers ?? {})

  if (!headers.has('Content-Type') && init.body) {
    headers.set('Content-Type', 'application/json')
  }

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  })

  if (response.status === 401) {
    throw new ApiError('Unauthorized', 401)
  }

  return response
}

export async function apiJson<T>(path: string, init: RequestInit = {}, token?: string | null): Promise<T> {
  const response = await apiFetch(path, init, token)

  if (!response.ok) {
    let message = `Request failed: ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) {
        message = payload.detail
      }
    } catch {
      // Ignore non-JSON error payloads.
    }
    throw new ApiError(message, response.status)
  }

  return (await response.json()) as T
}
