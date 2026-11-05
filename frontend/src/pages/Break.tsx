import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTestSession } from '../stores/testSession'
import { startModule } from '../api/attempts'
import { Button } from '../components/ui/Button'

const BREAK_SECONDS = 10 * 60

export function Break() {
  const navigate = useNavigate()
  const { moduleAttemptId } = useTestSession()
  const [secondsLeft, setSecondsLeft] = useState(BREAK_SECONDS)

  async function resumeNextModule() {
    if (!moduleAttemptId) {
      // Fallback — no stored module ID, go home
      navigate('/')
      return
    }
    await startModule(moduleAttemptId)
    navigate(`/take/${moduleAttemptId}`)
  }

  useEffect(() => {
    const interval = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          clearInterval(interval)
          resumeNextModule()
          return 0
        }
        return s - 1
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [navigate, moduleAttemptId])

  const minutes = Math.floor(secondsLeft / 60)
  const secs = secondsLeft % 60

  return (
    <main className="min-h-screen bg-blue-50 flex items-center justify-center">
      <div className="bg-white rounded-xl shadow-md p-10 text-center max-w-sm w-full">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Break Time</h1>
        <p className="text-gray-500 text-sm mb-8">
          Section 1 complete. Take a breather before Section 2.
        </p>

        <div
          aria-live="polite"
          aria-label="Break time remaining"
          className="text-6xl font-mono font-bold text-blue-700 mb-8"
        >
          {String(minutes).padStart(2, '0')}:{String(secs).padStart(2, '0')}
        </div>

        <Button size="lg" onClick={resumeNextModule}>
          Start Section 2 Now
        </Button>
      </div>
    </main>
  )
}
