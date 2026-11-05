import { create } from 'zustand'

interface TestSessionState {
  userId: string
  attemptId: string | null
  moduleAttemptId: string | null
  currentQuestionIndex: number
  submitResult: Record<string, unknown> | null

  setUserId: (id: string) => void
  setSession: (attemptId: string, maId: string) => void
  setModuleAttemptId: (maId: string) => void
  setCurrentQuestionIndex: (i: number) => void
  setSubmitResult: (r: Record<string, unknown> | null) => void
  reset: () => void
}

export const useTestSession = create<TestSessionState>((set) => ({
  userId: localStorage.getItem('userId') ?? '',
  attemptId: null,
  moduleAttemptId: null,
  currentQuestionIndex: 0,
  submitResult: null,

  setUserId: (id) => {
    localStorage.setItem('userId', id)
    set({ userId: id })
  },
  setSession: (attemptId, maId) =>
    set({ attemptId, moduleAttemptId: maId }),
  setModuleAttemptId: (maId) =>
    set({ moduleAttemptId: maId }),
  setCurrentQuestionIndex: (i) =>
    set({ currentQuestionIndex: i }),
  setSubmitResult: (r) => set({ submitResult: r }),
  reset: () => set({ attemptId: null, moduleAttemptId: null, currentQuestionIndex: 0, submitResult: null }),
}))
