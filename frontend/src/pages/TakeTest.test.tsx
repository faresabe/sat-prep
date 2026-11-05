import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { TakeTest } from './TakeTest'
import type { ModuleStateResponse } from '../types/api'

const MOCK_STATE: ModuleStateResponse = {
  module_attempt_id: 'ma-001',
  module_id: 'mod-001',
  status: 'in_progress',
  started_at: new Date(Date.now() - 60_000).toISOString(),
  deadline_at: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
  questions: [
    {
      id: 'q-001',
      section: 'RW',
      domain_id: 'd-001',
      skill_id: 's-001',
      passage_id: null,
      question_type: 'multiple_choice',
      stem: 'Which word best completes the sentence?',
      stem_asset_key: null,
      difficulty: 'easy',
      calculator_allowed: false,
      position: 1,
      choices: [
        { id: 'c-001', label: 'A', content: 'Choice A', asset_key: null, position: 1 },
        { id: 'c-002', label: 'B', content: 'Choice B', asset_key: null, position: 2 },
        { id: 'c-003', label: 'C', content: 'Choice C', asset_key: null, position: 3 },
        { id: 'c-004', label: 'D', content: 'Choice D', asset_key: null, position: 4 },
      ],
    },
  ],
  passages: {},
  answers: [],
}

const saveAnswerSpy = vi.fn()

const server = setupServer(
  http.get('*/api/v1/attempts/modules/:maId/state', () => {
    return HttpResponse.json(MOCK_STATE)
  }),
  http.post('*/api/v1/attempts/modules/:maId/answer', async ({ request }) => {
    const body = await request.json()
    saveAnswerSpy(body)
    return HttpResponse.json({
      id: 'ans-001',
      question_id: 'q-001',
      selected_choice_id: (body as { selected_choice_id: string }).selected_choice_id,
      response_text: null,
      eliminated_choice_ids: [],
      is_flagged: false,
      time_spent_ms: 0,
      visit_count: 1,
      revision: 1,
      updated_at: new Date().toISOString(),
    })
  }),
  http.post('*/api/v1/attempts/modules/:maId/submit', () => {
    return HttpResponse.json({
      module_attempt_id: 'ma-001',
      question_count: 1,
      correct_count: 1,
      weighted_score: 1.0,
      next: { type: 'attempt_complete' },
    })
  }),
)

beforeAll(() => server.listen())
afterEach(() => { server.resetHandlers(); saveAnswerSpy.mockClear() })
afterAll(() => server.close())

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/take/attempt-001/ma-001']}>
        <Routes>
          <Route path="/take/:attemptId/:maId" element={children} />
          <Route path="/result" element={<div>Result page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('TakeTest', () => {
  it('renders question after loading', async () => {
    const Wrapper = makeWrapper()
    render(<TakeTest />, { wrapper: Wrapper })

    await waitFor(() => {
      expect(screen.getByText(/Which word best completes/)).toBeInTheDocument()
    })
  })

  it('autosaves when a choice is selected', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const Wrapper = makeWrapper()
    render(<TakeTest />, { wrapper: Wrapper })

    await waitFor(() => {
      expect(screen.getByText('Choice A')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('radio', { name: /Choice A: Choice A/ }))

    // Advance debounce timer
    vi.advanceTimersByTime(600)

    await waitFor(() => {
      expect(saveAnswerSpy).toHaveBeenCalledWith(
        expect.objectContaining({ selected_choice_id: 'c-001' }),
      )
    })

    vi.useRealTimers()
  })
})
