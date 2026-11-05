import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { App } from './App'

createRoot(document.getElementById('root')!).render(
  // StrictMode disabled during dev — it double-fires mutations which breaks idempotency testing
  <App />
)
