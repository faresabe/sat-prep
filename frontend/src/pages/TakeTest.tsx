import { useState, useCallback, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { useAttemptState } from '../hooks/useAttemptState'
import { useAutosave } from '../hooks/useAutosave'
import { Timer } from '../components/test/Timer'
import { QuestionCard } from '../components/test/QuestionCard'
import { Passage } from '../components/test/Passage'
import { Toolbar } from '../components/test/Toolbar'
import { Navigator } from '../components/test/Navigator'
import { Modal } from '../components/ui/Modal'
import { Button } from '../components/ui/Button'
import { submitModule, startModule } from '../api/attempts'
import { useTestSession } from '../stores/testSession'
import type { Answer, NextAction } from '../types/api'

export function TakeTest() {
  const { maId = '' } = useParams<{ maId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { setModuleAttemptId, setSubmitResult } = useTestSession()

  const { data: state, isLoading, error } = useAttemptState(maId)
  const { save: autosave } = useAutosave(maId)

  const [currentIdx, setCurrentIdx] = useState(0)
  const [eliminateMode, setEliminateMode] = useState(false)
  const [showNavigator, setShowNavigator] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [timerHidden, setTimerHidden] = useState(false)
  const [localAnswers, setLocalAnswers] = useState<Map<string, Partial<Answer>>>(new Map())
  const revisionRef = useRef<Map<string, number>>(new Map())

  // Sync server answers into local map on first load
  useEffect(() => {
    if (!state) return
    const m = new Map<string, Partial<Answer>>()
    const r = new Map<string, number>()
    state.answers.forEach((a) => {
      m.set(a.question_id, a)
      r.set(a.question_id, a.revision)
    })
    setLocalAnswers(m)
    revisionRef.current = r
  }, [state?.module_attempt_id]) // only on module change

  // Auto-start module if it's not_started (e.g., after navigating from Module 1 submit)
  useEffect(() => {
    if (!state || state.status !== 'not_started') return
    startModule(maId).then(() => {
      qc.invalidateQueries({ queryKey: ['moduleState', maId] })
    }).catch(() => {
      // If start fails, refetch to show current state
      qc.invalidateQueries({ queryKey: ['moduleState', maId] })
    })
  }, [state?.status, maId])

  const [submitError, setSubmitError] = useState<string | null>(null)

  const submitMutation = useMutation({
    mutationFn: (reason: string) => submitModule(maId, reason),
    onSuccess: (result) => {
      setSubmitError(null)
      setSubmitResult(result as unknown as Record<string, unknown>)
      const next = result.next as NextAction
      if (next.type === 'next_module') {
        // Navigate immediately — TakeTest will auto-start the module
        setModuleAttemptId(next.module_attempt_id)
        // Hard navigation — more reliable than navigate() inside mutation callbacks
        window.location.href = `/take/${next.module_attempt_id}`
      } else if (next.type === 'break') {
        // Store the next module_attempt_id so Break.tsx can resume it
        navigate('/break')
      } else {
        navigate('/result')
      }
    },
    onError: (err: unknown) => {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })
        ?.response?.status
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? 'Submit failed. Please try again.'
      if (status === 409) {
        setSubmitError('This module has already been submitted.')
      } else {
        setSubmitError(detail)
      }
    },
  })

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (!state) return
      const q = state.questions[currentIdx]
      if (!q) return

      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        setCurrentIdx((i) => Math.min(i + 1, state.questions.length - 1))
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        setCurrentIdx((i) => Math.max(i - 1, 0))
      } else if (e.key === 'f' || e.key === 'F') {
        handleFlag(q.id)
      } else {
        const n = parseInt(e.key)
        if (n >= 1 && n <= 4 && q.choices[n - 1]) {
          handleSelect(q.id, q.choices[n - 1].id)
        }
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [state, currentIdx])

  const getLocalAnswer = (questionId: string): Answer | undefined => {
    const local = localAnswers.get(questionId)
    const server = state?.answers.find((a) => a.question_id === questionId)
    return (local || server) as Answer | undefined
  }

  const nextRevision = (questionId: string): number => {
    const current = revisionRef.current.get(questionId) ?? 0
    const next = current + 1
    revisionRef.current.set(questionId, next)
    return next
  }

  const handleSelect = useCallback((questionId: string, choiceId: string) => {
    if (!state || state.status !== 'in_progress') return
    const existing = getLocalAnswer(questionId)
    const revision = nextRevision(questionId)

    setLocalAnswers((prev) => {
      const next = new Map(prev)
      next.set(questionId, {
        ...existing,
        question_id: questionId,
        selected_choice_id: choiceId,
        revision,
      })
      return next
    })

    autosave({
      question_id: questionId,
      selected_choice_id: choiceId,
      eliminated_choice_ids: existing?.eliminated_choice_ids ?? [],
      is_flagged: existing?.is_flagged ?? false,
      time_spent_ms: existing?.time_spent_ms ?? 0,
      revision,
    })
  }, [state, localAnswers, autosave])

  const handleEliminate = useCallback((questionId: string, choiceId: string) => {
    const existing = getLocalAnswer(questionId)
    const currentEliminated = existing?.eliminated_choice_ids ?? []
    const newEliminated = currentEliminated.includes(choiceId)
      ? currentEliminated.filter((id) => id !== choiceId)
      : [...currentEliminated, choiceId]
    const revision = nextRevision(questionId)

    setLocalAnswers((prev) => {
      const next = new Map(prev)
      next.set(questionId, {
        ...existing,
        question_id: questionId,
        eliminated_choice_ids: newEliminated,
        revision,
      })
      return next
    })

    autosave({
      question_id: questionId,
      selected_choice_id: existing?.selected_choice_id ?? null,
      eliminated_choice_ids: newEliminated,
      is_flagged: existing?.is_flagged ?? false,
      time_spent_ms: existing?.time_spent_ms ?? 0,
      revision,
    })
  }, [localAnswers, autosave])

  const handleFlag = useCallback((questionId: string) => {
    const existing = getLocalAnswer(questionId)
    const revision = nextRevision(questionId)
    const newFlagged = !(existing?.is_flagged ?? false)

    setLocalAnswers((prev) => {
      const next = new Map(prev)
      next.set(questionId, { ...existing, question_id: questionId, is_flagged: newFlagged, revision })
      return next
    })

    autosave({
      question_id: questionId,
      selected_choice_id: existing?.selected_choice_id ?? null,
      eliminated_choice_ids: existing?.eliminated_choice_ids ?? [],
      is_flagged: newFlagged,
      time_spent_ms: existing?.time_spent_ms ?? 0,
      revision,
    })
  }, [localAnswers, autosave])

  const handleTextInput = useCallback((questionId: string, text: string) => {
    if (!state || state.status !== 'in_progress') return
    const existing = getLocalAnswer(questionId)
    const revision = nextRevision(questionId)

    setLocalAnswers((prev) => {
      const next = new Map(prev)
      next.set(questionId, {
        ...existing,
        question_id: questionId,
        response_text: text,
        revision,
      })
      return next
    })

    autosave({
      question_id: questionId,
      selected_choice_id: existing?.selected_choice_id ?? null,
      response_text: text,
      eliminated_choice_ids: existing?.eliminated_choice_ids ?? [],
      is_flagged: existing?.is_flagged ?? false,
      time_spent_ms: existing?.time_spent_ms ?? 0,
      revision,
    })
  }, [state, localAnswers, autosave])

  const handleSubmit = (reason = 'user') => {
    submitMutation.mutate(reason)
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">Loading module…</p>
      </div>
    )
  }

  if (error || !state) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-red-600">Failed to load module. Please try again.</p>
      </div>
    )
  }

  // Module is not_started — auto-start effect is running, show loading
  if (state.status === 'not_started') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">Starting module…</p>
      </div>
    )
  }

  const questions = state.questions
  const currentQ = questions[currentIdx]
  const currentAnswer = getLocalAnswer(currentQ.id)
  const passage = currentQ.passage_id ? state.passages[currentQ.passage_id] : null
  const hasPassage = !!passage

  // Build answer list merging local optimistic state
  const mergedAnswers: Answer[] = questions.map((q) => {
    return (getLocalAnswer(q.id) as Answer) ?? ({ question_id: q.id } as Answer)
  })

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b px-4 py-2 flex items-center gap-4">
        <span className="font-semibold text-gray-800 text-sm">
          Module {state.module_id.slice(0, 8)}
        </span>
        <div className="ml-auto flex items-center gap-3">
          <Timer
            deadlineAt={state.deadline_at}
            onExpire={() => handleSubmit('timeout')}
            hidden={timerHidden}
          />
        </div>
      </header>

      {/* Toolbar */}
      <div className="bg-white border-b px-4 py-2">
        <Toolbar
          eliminateMode={eliminateMode}
          onToggleEliminate={() => setEliminateMode((x) => !x)}
          onOpenNavigator={() => setShowNavigator(true)}
          isSubmitting={submitMutation.isPending}
          onSubmit={() => setShowConfirm(true)}
          onToggleTimer={() => setTimerHidden((x) => !x)}
          timerHidden={timerHidden}
        />
      </div>

      {/* Main content */}
      <div className={`flex-1 flex ${hasPassage ? 'flex-row' : 'flex-col'} overflow-hidden`}>
        {hasPassage && passage && (
          <div className="w-1/2 p-6 border-r bg-white overflow-y-auto">
            <Passage content={passage.content} source={passage.source} />
          </div>
        )}

        <div className={`${hasPassage ? 'w-1/2' : 'max-w-3xl mx-auto w-full'} p-6 overflow-y-auto`}>
          <QuestionCard
            question={currentQ}
            position={currentIdx + 1}
            answer={currentAnswer}
            eliminateMode={eliminateMode}
            onSelect={(choiceId) => handleSelect(currentQ.id, choiceId)}
            onEliminate={(choiceId) => handleEliminate(currentQ.id, choiceId)}
            onFlag={() => handleFlag(currentQ.id)}
            onTextInput={(text) => handleTextInput(currentQ.id, text)}
          />
        </div>
      </div>

      {/* Footer navigation */}
      <footer className="bg-white border-t px-6 py-3 flex items-center justify-between">
        <Button
          variant="secondary"
          disabled={currentIdx === 0}
          onClick={() => setCurrentIdx((i) => i - 1)}
        >
          ← Previous
        </Button>
        <span className="text-sm text-gray-500">
          {currentIdx + 1} / {questions.length}
        </span>
        <Button
          variant={currentIdx < questions.length - 1 ? 'secondary' : 'primary'}
          onClick={() => {
            if (currentIdx < questions.length - 1) {
              setCurrentIdx((i) => i + 1)
            } else {
              setShowConfirm(true)
            }
          }}
        >
          {currentIdx < questions.length - 1 ? 'Next →' : 'Review & Submit'}
        </Button>
      </footer>

      {/* Navigator sidebar */}
      {showNavigator && (
        <Navigator
          questions={questions}
          answers={mergedAnswers}
          currentIndex={currentIdx}
          onNavigate={setCurrentIdx}
          onClose={() => setShowNavigator(false)}
        />
      )}

      {/* Submit confirm modal */}
      <Modal
        open={showConfirm}
        onClose={() => { setShowConfirm(false); setSubmitError(null) }}
        title="Submit Module"
      >
        <p className="text-gray-600 text-sm mb-4">
          Are you sure you want to submit? You won't be able to change your answers.
        </p>
        {submitError && (
          <p role="alert" className="text-red-600 text-sm mb-4">{submitError}</p>
        )}
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => { setShowConfirm(false); setSubmitError(null) }}>
            Go Back
          </Button>
          <Button
            onClick={() => { setShowConfirm(false); handleSubmit('user') }}
            disabled={submitMutation.isPending}
          >
            {submitMutation.isPending ? 'Submitting…' : 'Submit'}
          </Button>
        </div>
      </Modal>
    </div>
  )
}
