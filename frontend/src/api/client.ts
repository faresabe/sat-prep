import axios from 'axios'
import { v4 as uuidv4 } from 'uuid'

// VITE_API_URL must be set as an environment variable in Vercel.
// Falls back to localhost only in local dev (when import.meta.env.DEV is true).
const API_URL: string =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.DEV ? 'http://localhost:8000' : '')

if (!API_URL) {
  console.error('VITE_API_URL is not set. Set it in the Vercel environment variables.')
}

const client = axios.create({
  baseURL: API_URL,
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
