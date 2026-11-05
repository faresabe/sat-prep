import axios from 'axios'
import { v4 as uuidv4 } from 'uuid'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
  timeout: 15_000,
})

// Attach X-User-Id from localStorage on every request
client.interceptors.request.use((config) => {
  const userId = localStorage.getItem('userId')
  if (userId) {
    config.headers['X-User-Id'] = userId
  }

  // Auto-add Idempotency-Key for mutating requests
  if (['post', 'patch', 'put'].includes(config.method?.toLowerCase() ?? '')) {
    if (!config.headers['Idempotency-Key']) {
      config.headers['Idempotency-Key'] = uuidv4()
    }
  }

  return config
})

// Response interceptors
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (import.meta.env.DEV) {
      console.error(
        `[API Error] ${err.config?.method?.toUpperCase()} ${err.config?.url}`,
        err.response?.status,
        err.response?.data,
      )
    }
    if (err.response?.status === 401) {
      localStorage.removeItem('userId')
      window.location.href = '/'
    }
    return Promise.reject(err)
  },
)

export default client
