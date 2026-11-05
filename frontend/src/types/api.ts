// API response types matching backend Pydantic schemas

export interface StartAttemptResponse {
  attempt_id: string
  module_attempt_id: string
}

export interface StartModuleResponse {
  module_attempt_id: string
  status: string
  started_at: string | null
  deadline_at: string | null
}

export interface Choice {
  id: string
  label: string
  content: string
  asset_key: string | null
  position: number
}

export interface Question {
  id: string
  section: string
  domain_id: string
  skill_id: string
  passage_id: string | null
  question_type: 'multiple_choice' | 'grid_in'
  stem: string
  stem_asset_key: string | null
  difficulty: string
  calculator_allowed: boolean
  position: number
  choices: Choice[]
}

export interface Passage {
  id: string
  content: string
  asset_key: string | null
  source: string | null
}

export interface Answer {
  id: string
  question_id: string
  selected_choice_id: string | null
  response_text: string | null
  eliminated_choice_ids: string[]
  is_flagged: boolean
  time_spent_ms: number
  visit_count: number
  revision: number
  updated_at: string
}

export interface ModuleStateResponse {
  module_attempt_id: string
  module_id: string
  status: string
  started_at: string | null
  deadline_at: string | null
  questions: Question[]
  passages: Record<string, Passage>
  answers: Answer[]
}

export interface SaveAnswerBody {
  question_id: string
  selected_choice_id?: string | null
  response_text?: string | null
  eliminated_choice_ids: string[]
  is_flagged: boolean
  time_spent_ms: number
  revision: number
}

export interface SubmitResult {
  module_attempt_id: string
  question_count: number
  correct_count: number
  weighted_score: number
  next: NextAction
}

export type NextAction =
  | { type: 'next_module'; module_attempt_id: string; level: string; weighted_score: number; threshold: number }
  | { type: 'break'; break_session_id: string }
  | { type: 'attempt_complete' }

export interface MeStats {
  total_attempts: number
  best_score: number | null
  latest_score: number | null
  latest_attempt_id: string | null
  overall_accuracy: number | null
}

export interface SkillStat {
  skill_id: string
  skill_code: string
  skill_name: string
  domain: string
  total: number
  correct: number
  accuracy_pct: number | null
}

export interface DomainStat {
  domain_id: string
  domain_code: string
  domain_name: string
  total: number
  correct: number
  accuracy_pct: number | null
}

export interface AttemptHistory {
  attempt_id: string
  started_at: string
  completed_at: string | null
  rw_raw: number | null
  rw_scaled: number | null
  stage2_level: string | null
}
