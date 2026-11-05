import type { Question, Answer } from '../../types/api'

interface NavigatorProps {
  questions: Question[]
  answers: Answer[]
  currentIndex: number
  onNavigate: (index: number) => void
  onClose: () => void
}

export function Navigator({
  questions,
  answers,
  currentIndex,
  onNavigate,
  onClose,
}: NavigatorProps) {
  const answerMap = new Map(answers.map((a) => [a.question_id, a]))

  return (
    <div
      role="navigation"
      aria-label="Question navigator"
      className="fixed inset-y-0 right-0 w-72 bg-white shadow-xl z-40 flex flex-col"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <h3 className="font-semibold text-gray-800">Question Navigator</h3>
        <button
          onClick={onClose}
          aria-label="Close navigator"
          className="text-gray-400 hover:text-gray-700 text-xl"
        >
          ×
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="grid grid-cols-5 gap-2">
          {questions.map((q, i) => {
            const ans = answerMap.get(q.id)
            const isAnswered = !!(ans?.selected_choice_id || ans?.response_text)
            const isFlagged = ans?.is_flagged
            const isCurrent = i === currentIndex

            return (
              <button
                key={q.id}
                onClick={() => { onNavigate(i); onClose() }}
                aria-label={`Question ${i + 1}${isFlagged ? ', flagged' : ''}${isAnswered ? ', answered' : ', unanswered'}`}
                aria-current={isCurrent ? 'true' : undefined}
                className={`w-full aspect-square rounded-md text-sm font-medium transition-colors
                  ${isCurrent ? 'ring-2 ring-blue-600' : ''}
                  ${isFlagged ? 'bg-amber-100 text-amber-800 border-amber-300 border' : ''}
                  ${isAnswered && !isFlagged ? 'bg-blue-600 text-white' : ''}
                  ${!isAnswered && !isFlagged ? 'bg-gray-100 text-gray-600 hover:bg-gray-200' : ''}
                `}
              >
                {i + 1}
              </button>
            )
          })}
        </div>
      </div>

      <div className="p-4 border-t text-xs text-gray-500 space-y-1">
        <div className="flex items-center gap-2">
          <span className="w-4 h-4 rounded bg-blue-600 inline-block" /> Answered
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-4 rounded bg-amber-100 border border-amber-300 inline-block" /> Flagged
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-4 rounded bg-gray-100 inline-block" /> Unanswered
        </div>
      </div>
    </div>
  )
}
