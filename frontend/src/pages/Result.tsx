import { useNavigate } from 'react-router-dom'
import { useTestSession } from '../stores/testSession'
import { Button } from '../components/ui/Button'

export function Result() {
  const navigate = useNavigate()
  const { submitResult, reset } = useTestSession()

  const result = submitResult as {
    module_attempt_id?: string
    question_count?: number
    correct_count?: number
    weighted_score?: number
    next?: { type: string; level?: string; weighted_score?: number; threshold?: number }
  } | null

  function handleDone() {
    reset()
    navigate('/')
  }

  if (!result) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600 mb-4">No result data found.</p>
          <Button onClick={() => navigate('/')}>Go Home</Button>
        </div>
      </main>
    )
  }

  const pct = result.question_count
    ? Math.round(((result.correct_count ?? 0) / result.question_count) * 100)
    : 0

  const routing = result.next?.type === 'next_module' ? result.next : null
  const level = routing?.level

  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-md max-w-lg w-full p-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Module Complete</h1>

        <div className="grid grid-cols-2 gap-4 mb-8">
          <div className="bg-blue-50 rounded-lg p-4 text-center">
            <p className="text-sm text-blue-600 font-medium mb-1">Correct</p>
            <p className="text-3xl font-bold text-blue-800">
              {result.correct_count} / {result.question_count}
            </p>
          </div>
          <div className="bg-green-50 rounded-lg p-4 text-center">
            <p className="text-sm text-green-600 font-medium mb-1">Score</p>
            <p className="text-3xl font-bold text-green-800">{pct}%</p>
          </div>
        </div>

        {level && (
          <div
            className={`rounded-lg p-4 mb-6 text-center ${
              level === 'hard'
                ? 'bg-purple-50 border border-purple-200'
                : 'bg-orange-50 border border-orange-200'
            }`}
          >
            <p className="text-sm font-medium text-gray-500 mb-1">Routing Decision</p>
            <p className={`text-xl font-bold ${level === 'hard' ? 'text-purple-800' : 'text-orange-800'}`}>
              {level === 'hard' ? '🚀 Hard Module' : '📚 Easy Module'}
            </p>
            <p className="text-xs text-gray-400 mt-1">
              Score {Math.round((routing?.weighted_score ?? 0) * 100)}% vs threshold{' '}
              {Math.round((routing?.threshold ?? 0) * 100)}%
            </p>
          </div>
        )}

        {result.next?.type === 'attempt_complete' && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6 text-center">
            <p className="text-green-800 font-semibold">Test Complete! Score report generated.</p>
          </div>
        )}

        <div className="flex gap-3">
          <Button variant="secondary" onClick={handleDone} className="flex-1">
            Take Another Test
          </Button>
          <Button onClick={() => navigate('/dashboard')} className="flex-1">
            View Dashboard
          </Button>
        </div>
      </div>
    </main>
  )
}
