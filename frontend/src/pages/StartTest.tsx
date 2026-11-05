import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { startAttempt, startModule } from '../api/attempts'
import { useTestSession } from '../stores/testSession'

// ─── Dev config — hardcoded to skip login form ───────────────────────────────
const DEV_USER_ID = 'd0712ba7-cac5-4ab9-b9b2-1d7c148a4955'
const DEV_TEST_ID = '61ef9e99-3ef5-41e2-b967-34d338e95109'
// ─────────────────────────────────────────────────────────────────────────────

export function StartTest() {
  const navigate = useNavigate()
  const { setUserId, setSession } = useTestSession()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function autoStart() {
      try {
        setUserId(DEV_USER_ID)

        const { attempt_id, module_attempt_id } = await startAttempt(DEV_TEST_ID)
        await startModule(module_attempt_id)

        setSession(attempt_id, module_attempt_id)
        navigate(`/take/${attempt_id}/${module_attempt_id}`)
      } catch (err: unknown) {
        const msg =
          (err as { response?: { data?: { detail?: string } } })
            ?.response?.data?.detail ?? 'Failed to start test.'
        setError(msg)
      }
    }

    autoStart()
  }, [])

  if (error) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 mb-4">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="text-blue-600 underline text-sm"
          >
            Retry
          </button>
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center">
      <p className="text-gray-500 text-sm">Starting test…</p>
    </main>
  )
}
