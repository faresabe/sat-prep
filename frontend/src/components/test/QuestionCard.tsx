import type { Question, Answer } from '../../types/api'
import { ChoiceList } from './ChoiceList'

interface QuestionCardProps {
  question: Question
  position: number
  answer: Answer | undefined
  eliminateMode: boolean
  onSelect: (choiceId: string) => void
  onEliminate: (choiceId: string) => void
  onFlag: () => void
  onTextInput: (text: string) => void
}

export function QuestionCard({
  question,
  position,
  answer,
  eliminateMode,
  onSelect,
  onEliminate,
  onFlag,
  onTextInput,
}: QuestionCardProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-500">
          Question {position}
        </span>
        <button
          onClick={onFlag}
          aria-label={answer?.is_flagged ? 'Remove flag' : 'Flag for review'}
          aria-pressed={answer?.is_flagged ?? false}
          className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border transition-colors
            ${answer?.is_flagged
              ? 'bg-amber-50 border-amber-400 text-amber-700'
              : 'bg-white border-gray-200 text-gray-500 hover:border-gray-400'}`}
        >
          🔖 {answer?.is_flagged ? 'Marked' : 'Mark for Review'}
        </button>
      </div>

      <div
        className="text-gray-900 leading-relaxed"
        dangerouslySetInnerHTML={{ __html: question.stem }}
      />

      {question.question_type === 'multiple_choice' ? (
        <ChoiceList
          choices={question.choices}
          selectedId={answer?.selected_choice_id ?? null}
          eliminatedIds={answer?.eliminated_choice_ids ?? []}
          onSelect={onSelect}
          onEliminate={onEliminate}
          eliminateMode={eliminateMode}
        />
      ) : (
        <div className="mt-2">
          <label htmlFor="grid-in" className="block text-sm text-gray-600 mb-1">
            Your answer
          </label>
          <input
            id="grid-in"
            type="text"
            value={answer?.response_text ?? ''}
            maxLength={30}
            placeholder="Enter your answer"
            onChange={(e) => onTextInput(e.target.value)}
            className="border-2 border-gray-300 rounded-md px-3 py-2 text-gray-900 w-40
              focus:outline-none focus:border-blue-500"
          />
        </div>
      )}
    </div>
  )
}
