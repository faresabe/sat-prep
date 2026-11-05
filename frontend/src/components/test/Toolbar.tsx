interface ToolbarProps {
  eliminateMode: boolean
  onToggleEliminate: () => void
  onOpenNavigator: () => void
  isSubmitting: boolean
  onSubmit: () => void
  onToggleTimer: () => void
  timerHidden: boolean
}

export function Toolbar({
  eliminateMode,
  onToggleEliminate,
  onOpenNavigator,
  isSubmitting,
  onSubmit,
  onToggleTimer,
  timerHidden,
}: ToolbarProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button
        onClick={onToggleEliminate}
        aria-pressed={eliminateMode}
        className={`px-3 py-1.5 text-sm rounded-md border transition-colors
          ${eliminateMode ? 'bg-red-50 border-red-400 text-red-700' : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'}`}
      >
        ✕ Cross Out
      </button>

      <button
        onClick={onToggleTimer}
        aria-label={timerHidden ? 'Show timer' : 'Hide timer'}
        className="px-3 py-1.5 text-sm rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50"
      >
        ⏱ {timerHidden ? 'Show' : 'Hide'} Timer
      </button>

      <button
        onClick={onOpenNavigator}
        className="px-3 py-1.5 text-sm rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50"
      >
        ☰ Navigator
      </button>

      <button
        onClick={onSubmit}
        disabled={isSubmitting}
        className="ml-auto px-4 py-1.5 text-sm rounded-md bg-blue-700 text-white
          hover:bg-blue-800 disabled:opacity-50 font-medium"
      >
        {isSubmitting ? 'Submitting…' : 'Review & Submit'}
      </button>
    </div>
  )
}
