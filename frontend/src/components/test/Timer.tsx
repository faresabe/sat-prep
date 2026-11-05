import { useTimer, formatTime } from '../../hooks/useTimer'

interface TimerProps {
  deadlineAt: string | null | undefined
  onExpire: () => void
  hidden?: boolean
}

export function Timer({ deadlineAt, onExpire, hidden }: TimerProps) {
  const { secondsLeft, paused, togglePause } = useTimer(deadlineAt, onExpire)

  if (hidden) return null

  const isLow = secondsLeft !== null && secondsLeft < 300
  const isUrgent = secondsLeft !== null && secondsLeft < 60

  return (
    <div className="flex items-center gap-2">
      <div
        aria-label="Time remaining"
        aria-live="polite"
        className={`font-mono text-lg font-semibold tabular-nums px-3 py-1 rounded
          ${paused ? 'text-gray-500 bg-gray-100' : isUrgent ? 'text-red-700 bg-red-50' : isLow ? 'text-amber-700 bg-amber-50' : 'text-gray-700'}`}
      >
        {formatTime(secondsLeft)}
      </div>
      <button
        onClick={togglePause}
        aria-label={paused ? 'Resume timer' : 'Pause timer'}
        aria-pressed={paused}
        className="text-sm px-2 py-1 rounded border border-gray-200 text-gray-500 hover:border-gray-400 hover:text-gray-700 transition-colors"
      >
        {paused ? '▶' : '⏸'}
      </button>
    </div>
  )
}
