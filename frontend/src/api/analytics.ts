import client from './client'
import type { MeStats, SkillStat, DomainStat, AttemptHistory } from '../types/api'

export const getMe = (): Promise<MeStats> =>
  client.get<MeStats>('/api/v1/analytics/me').then((r) => r.data)

export const getSkillStats = (): Promise<SkillStat[]> =>
  client.get<SkillStat[]>('/api/v1/analytics/me/skills').then((r) => r.data)

export const getDomainStats = (): Promise<DomainStat[]> =>
  client.get<DomainStat[]>('/api/v1/analytics/me/domains').then((r) => r.data)

export const getAttemptHistory = (): Promise<AttemptHistory[]> =>
  client.get<AttemptHistory[]>('/api/v1/analytics/me/attempts').then((r) => r.data)
