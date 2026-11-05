import type { Choice } from '../../types/api'

interface ChoiceListProps {
  choices: Choice[]
  selectedId: string | null
  eliminatedIds: string[]
  onSelect: (choiceId: string) => void
  onEliminate: (choiceId: string) => void
  eliminateMode: boolean
}

export function ChoiceList({
  choices,
  selectedId,
  eliminatedIds,
  onSelect,
  onEliminate,
  eliminateMode,
}: ChoiceListProps) {
  return (
    <div role="radiogroup" aria-label="Answer choices" className="space-y-3">
      {choices.map((choice, i) => {
        const isSelected = selectedId === choice.id
        const isEliminated = eliminatedIds.includes(choice.id)

        return (
          <div key={choice.id} className="flex items-start gap-2">
            <button
              role="radio"
              aria-checked={isSelected}
              aria-label={`Choice ${choice.label}: ${choice.content}`}
              disabled={isEliminated}
              onClick={() => !eliminateMode && onSelect(choice.id)}
              onKeyDown={(e) => {
                const n = parseInt(e.key)
                if (n >= 1 && n <= 4 && n === i + 1) onSelect(choice.id)
              }}
              className={`flex-1 flex items-start gap-3 px-4 py-3 rounded-lg border-2 text-left
                transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600
                ${isEliminated ? 'opacity-40 line-through cursor-not-allowed border-gray-200 bg-gray-50' : ''}
                ${isSelected && !isEliminated ? 'border-blue-600 bg-blue-50' : 'border-gray-200 hover:border-gray-400 bg-white'}
              `}
            >
              <span className={`flex-shrink-0 w-7 h-7 rounded-full border-2 flex items-center justify-center text-sm font-semibold
                ${isSelected && !isEliminated ? 'border-blue-600 bg-blue-600 text-white' : 'border-gray-300 text-gray-600'}`}>
                {choice.label}
              </span>
              <span className="text-gray-800 text-sm leading-relaxed"
                dangerouslySetInnerHTML={{ __html: choice.content }} />
            </button>

            {eliminateMode && (
              <button
                onClick={() => onEliminate(choice.id)}
                aria-label={`${isEliminated ? 'Restore' : 'Eliminate'} choice ${choice.label}`}
                className="mt-2.5 text-xs text-gray-400 hover:text-red-500 underline"
              >
                {isEliminated ? 'undo' : '✕'}
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}
