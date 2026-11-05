import { createBrowserRouter } from 'react-router-dom'
import { StartTest } from './pages/StartTest'
import { TakeTest } from './pages/TakeTest'
import { Break } from './pages/Break'
import { Result } from './pages/Result'
import { Dashboard } from './pages/Dashboard'

export const router = createBrowserRouter([
  { path: '/', element: <StartTest /> },
  {
    // Accept both /take/:attemptId/:maId (from start) and /take/:maId (continuing)
    path: '/take/:attemptId/:maId',
    element: <TakeTest />,
  },
  {
    path: '/take/:maId',
    element: <TakeTest />,
  },
  { path: '/break', element: <Break /> },
  { path: '/result', element: <Result /> },
  { path: '/dashboard', element: <Dashboard /> },
])
