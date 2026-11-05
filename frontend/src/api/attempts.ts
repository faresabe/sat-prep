import client from './client'
import type {
  StartAttemptResponse,
  StartModuleResponse,
  ModuleStateResponse,
  Answer,
  SaveAnswerBody,
  SubmitResult,
} from '../types/api'

export const startAttempt = (testId: string): Promise<StartAttemptResponse> =>
  client.post<StartAttemptResponse>('/api/v1/attempts/start', { test_id: testId })
    .then((r) => r.data)

export const startModule = (maId: string): Promise<StartModuleResponse> =>
  client.post<StartModuleResponse>(`/api/v1/attempts/modules/${maId}/start`)
    .then((r) => r.data)

export const getModuleState = (maId: string): Promise<ModuleStateResponse> =>
  client.get<ModuleStateResponse>(`/api/v1/attempts/modules/${maId}/state`)
    .then((r) => r.data)

export const saveAnswer = (maId: string, body: SaveAnswerBody): Promise<Answer> =>
  client.post<Answer>(`/api/v1/attempts/modules/${maId}/answer`, body)
    .then((r) => r.data)

export const submitModule = (maId: string, reason = 'user'): Promise<SubmitResult> =>
  client.post<SubmitResult>(
    `/api/v1/attempts/modules/${maId}/submit`,
    null,
    { params: { reason } }
  ).then((r) => r.data)
