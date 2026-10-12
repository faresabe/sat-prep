-- ============================================================================
--  SAT PREP PLATFORM - COMPLETE DATABASE BUILD (PostgreSQL 15+)
--  Tested end to end on PostgreSQL 16.
--
--  HOW TO RUN:
--    1. Edit the CHANGE_ME_* passwords in STEP 1 below (and keep them for your app).
--    2. Run as the PostgreSQL superuser:   psql -h localhost -U postgres -f build_all.sql
--    3. When the script reaches "\connect satprep app_owner" it asks for the app_owner password.
--  Do NOT run it with --single-transaction (CREATE DATABASE cannot run inside a transaction).
--  Run it once on an empty server. To start over: DROP DATABASE satprep; then drop the 8 roles.
-- ============================================================================
\set ON_ERROR_STOP on

\echo === STEP 1: Create the roles and the database (as postgres) ===
-- Run as the PostgreSQL superuser (postgres). Replace every CHANGE_ME_* password first.
CREATE ROLE app_owner         LOGIN PASSWORD 'fares'   BYPASSRLS;
CREATE ROLE app_rw            LOGIN PASSWORD 'fares'      NOBYPASSRLS;
CREATE ROLE app_grader        LOGIN PASSWORD 'fares'  BYPASSRLS;
CREATE ROLE app_auth          LOGIN PASSWORD 'fares'    BYPASSRLS;
CREATE ROLE app_content_admin LOGIN PASSWORD 'fares' BYPASSRLS;
CREATE ROLE app_worker        LOGIN PASSWORD 'fares'  BYPASSRLS;
CREATE ROLE analytics_ro      LOGIN PASSWORD 'fares' NOBYPASSRLS;
CREATE ROLE backup_role       LOGIN PASSWORD 'fares'  NOBYPASSRLS;

CREATE DATABASE satprep OWNER app_owner ENCODING 'UTF8';
ALTER DATABASE satprep SET timezone TO 'UTC';
REVOKE ALL ON DATABASE satprep FROM PUBLIC;
GRANT CONNECT ON DATABASE satprep TO app_rw, app_grader, app_auth, app_content_admin, app_worker, analytics_ro, backup_role;
GRANT pg_read_all_data TO backup_role;   -- read-only access for backups (needs superuser to grant)

-- Safety limits for the API role
ALTER ROLE app_rw SET statement_timeout = '5s';
ALTER ROLE app_rw SET lock_timeout = '2s';
ALTER ROLE app_rw SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE app_grader SET statement_timeout = '10s';
ALTER ROLE app_grader SET lock_timeout = '2s';
ALTER ROLE app_grader SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE analytics_ro SET statement_timeout = '60s';

\connect satprep app_owner 

\echo === STEP 2: Create the `grading` schema and set schema privileges ===
-- Run as app_owner, connected to database satprep.
CREATE SCHEMA IF NOT EXISTS grading AUTHORIZATION app_owner;   -- answer keys live here
REVOKE ALL ON SCHEMA public  FROM PUBLIC;
REVOKE ALL ON SCHEMA grading FROM PUBLIC;
GRANT USAGE ON SCHEMA public  TO app_rw, app_grader, app_auth, app_content_admin, app_worker, analytics_ro, backup_role;
GRANT USAGE ON SCHEMA grading TO app_grader, app_content_admin;

\echo === STEP 3: Create the 16 enum types ===
CREATE TYPE user_role AS ENUM ('student', 'teacher', 'admin');
CREATE TYPE section_type AS ENUM ('RW', 'MATH');
CREATE TYPE question_type AS ENUM ('multiple_choice', 'grid_in');
CREATE TYPE difficulty_level AS ENUM ('easy', 'medium', 'hard');
CREATE TYPE content_status AS ENUM ('draft', 'in_review', 'published', 'archived');
CREATE TYPE test_type AS ENUM ('full_mock', 'section_practice', 'skill_practice');
CREATE TYPE module_level AS ENUM ('router', 'easy', 'hard');
CREATE TYPE attempt_status AS ENUM ('in_progress', 'completed', 'abandoned', 'voided');
CREATE TYPE module_attempt_status AS ENUM ('not_started', 'in_progress', 'submitted');
CREATE TYPE submit_reason AS ENUM ('user', 'timeout', 'admin', 'system');
CREATE TYPE answer_event_type AS ENUM ('visit', 'select', 'clear', 'flag', 'unflag', 'eliminate', 'restore');
CREATE TYPE consent_type AS ENUM ('terms_of_service', 'privacy_policy', 'parental_consent', 'marketing_email', 'analytics_cookies');
CREATE TYPE class_member_role AS ENUM ('student', 'co_teacher');
CREATE TYPE auth_event_type AS ENUM ('login_success', 'login_failed', 'logout', 'password_reset_requested', 'password_changed', 'email_verified', 'token_reuse_detected', 'account_locked', 'role_changed');
CREATE TYPE data_request_type AS ENUM ('export', 'delete');
CREATE TYPE data_request_status AS ENUM ('pending', 'processing', 'completed', 'failed');

\echo === STEP 4: Create helper functions ===
-- 1) updated_at maintenance
CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- 2) request context helpers used by Row-Level Security (set per transaction with SET LOCAL)
CREATE FUNCTION app_uid() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$;

CREATE FUNCTION app_role() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.role', true), '') $$;

-- 3) monthly partition creator for log tables
CREATE FUNCTION create_monthly_partitions(parent regclass, months_back int, months_ahead int)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  m date; sch text; pname text; part text;
BEGIN
  SELECT n.nspname, c.relname INTO sch, pname
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.oid = parent;
  FOR m IN
    SELECT g::date FROM generate_series(
      date_trunc('month', now()) - make_interval(months => months_back),
      date_trunc('month', now()) + make_interval(months => months_ahead),
      interval '1 month') AS g
  LOOP
    part := format('%s_p%s', pname, to_char(m, 'YYYYMM'));
    EXECUTE format('CREATE TABLE IF NOT EXISTS %I.%I PARTITION OF %s FOR VALUES FROM (%L) TO (%L)',
                   sch, part, parent, m, (m + interval '1 month')::date);
  END LOOP;
END $$;

\echo === STEP 5: Table 1 of 40: users ===
CREATE TABLE users (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  email varchar(320) NOT NULL,
  password_hash varchar(255) NOT NULL,
  full_name varchar(200),
  role user_role DEFAULT 'student' NOT NULL,
  is_active boolean DEFAULT true NOT NULL,
  email_verified_at timestamptz,
  last_login_at timestamptz,
  failed_login_count smallint DEFAULT 0 NOT NULL,
  locked_until timestamptz,
  password_changed_at timestamptz,
  target_score smallint,
  test_date date,
  timezone varchar(50),
  grade_level smallint,
  birth_year smallint,
  signup_source varchar(50),
  onboarding_completed_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT ck_users_email_normalised CHECK (email = lower(btrim(email)) AND position('@' in email) > 1),
  CONSTRAINT ck_users_target_score CHECK (target_score IS NULL OR target_score BETWEEN 400 AND 1600),
  CONSTRAINT ck_users_grade_level CHECK (grade_level IS NULL OR grade_level BETWEEN 9 AND 12),
  CONSTRAINT ck_users_birth_year CHECK (birth_year IS NULL OR birth_year BETWEEN 1900 AND 2100),
  CONSTRAINT ck_users_failed_login CHECK (failed_login_count >= 0)
);

CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email));
CREATE INDEX ix_users_role_active ON users USING btree (role) WHERE is_active;
CREATE INDEX ix_users_deleted_at ON users USING btree (deleted_at) WHERE deleted_at IS NOT NULL;

COMMENT ON TABLE users IS 'Every account on the platform (student, teacher, admin).';

\echo === STEP 6: Table 2 of 40: refresh_tokens ===
CREATE TABLE refresh_tokens (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  user_id uuid NOT NULL,
  family_id uuid NOT NULL,
  token_hash char(64) NOT NULL,
  replaced_by_id uuid,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  revoke_reason varchar(30),
  last_used_at timestamptz,
  user_agent varchar(500),
  ip inet,
  created_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_refresh_tokens_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_refresh_tokens_replaced_by_id FOREIGN KEY (replaced_by_id) REFERENCES refresh_tokens(id) ON DELETE SET NULL,
  CONSTRAINT uq_refresh_tokens_hash UNIQUE (token_hash),
  CONSTRAINT ck_refresh_tokens_expiry CHECK (expires_at > created_at)
);

CREATE INDEX ix_refresh_tokens_user_active ON refresh_tokens USING btree (user_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_refresh_tokens_family ON refresh_tokens USING btree (family_id);
CREATE INDEX ix_refresh_tokens_expires ON refresh_tokens USING btree (expires_at);

COMMENT ON TABLE refresh_tokens IS 'One row per logged-in device/session. Supports rotation and reuse detection.';

\echo === STEP 7: Table 3 of 40: password_reset_tokens ===
CREATE TABLE password_reset_tokens (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  user_id uuid NOT NULL,
  token_hash char(64) NOT NULL,
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  requested_ip inet,
  created_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_password_reset_tokens_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT uq_password_reset_hash UNIQUE (token_hash),
  CONSTRAINT ck_password_reset_expiry CHECK (expires_at > created_at)
);

CREATE INDEX ix_password_reset_user ON password_reset_tokens USING btree (user_id, created_at DESC);

COMMENT ON TABLE password_reset_tokens IS 'Single-use, short-lived password reset tokens.';

\echo === STEP 8: Table 4 of 40: email_verification_tokens ===
CREATE TABLE email_verification_tokens (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  user_id uuid NOT NULL,
  new_email varchar(320),
  token_hash char(64) NOT NULL,
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  created_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_email_verification_tokens_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT uq_email_verification_hash UNIQUE (token_hash)
);

COMMENT ON TABLE email_verification_tokens IS 'Email verification and email-change confirmation tokens.';

\echo === STEP 9: Table 5 of 40: user_consents ===
CREATE TABLE user_consents (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  user_id uuid NOT NULL,
  consent_type consent_type NOT NULL,
  document_version varchar(30) NOT NULL,
  granted_at timestamptz DEFAULT now() NOT NULL,
  revoked_at timestamptz,
  ip inet,
  guardian_email varchar(320),
  guardian_verified_at timestamptz,
  PRIMARY KEY (id),
  CONSTRAINT fk_user_consents_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT uq_user_consents_version UNIQUE (user_id, consent_type, document_version),
  CONSTRAINT ck_user_consents_revoked CHECK (revoked_at IS NULL OR revoked_at >= granted_at)
);

COMMENT ON TABLE user_consents IS 'Versioned record of legal consents (terms, privacy, parental consent, marketing).';

\echo === STEP 10: Table 6 of 40: auth_events ===
CREATE TABLE auth_events (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  created_at timestamptz DEFAULT now() NOT NULL,
  user_id uuid,
  event_type auth_event_type NOT NULL,
  identifier_hash char(64),
  ip inet,
  user_agent varchar(500),
  metadata jsonb,
  PRIMARY KEY (id, created_at),
  CONSTRAINT fk_auth_events_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
)
PARTITION BY RANGE (created_at);

CREATE INDEX ix_auth_events_user_created ON auth_events USING btree (user_id, created_at DESC);
CREATE INDEX ix_auth_events_ip_created ON auth_events USING btree (ip, created_at DESC);

COMMENT ON TABLE auth_events IS 'Append-only security log: logins, failures, resets, token reuse, lockouts.';

\echo === STEP 11: Table 7 of 40: classes ===
CREATE TABLE classes (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  teacher_id uuid NOT NULL,
  name varchar(120) NOT NULL,
  join_code varchar(12) NOT NULL,
  is_active boolean DEFAULT true NOT NULL,
  archived_at timestamptz,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_classes_teacher_id FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT uq_classes_join_code UNIQUE (join_code)
);

CREATE INDEX ix_classes_teacher ON classes USING btree (teacher_id) WHERE is_active;

COMMENT ON TABLE classes IS 'A teacher''s class / cohort. Defines which students a teacher may see.';

\echo === STEP 12: Table 8 of 40: class_members ===
CREATE TABLE class_members (
  class_id uuid NOT NULL,
  user_id uuid NOT NULL,
  member_role class_member_role DEFAULT 'student' NOT NULL,
  results_visible_to_teacher boolean DEFAULT true NOT NULL,
  joined_at timestamptz DEFAULT now() NOT NULL,
  removed_at timestamptz,
  PRIMARY KEY (class_id, user_id),
  CONSTRAINT fk_class_members_class_id FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
  CONSTRAINT fk_class_members_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT ck_class_members_removed CHECK (removed_at IS NULL OR removed_at >= joined_at)
);

CREATE INDEX ix_class_members_user ON class_members USING btree (user_id) WHERE removed_at IS NULL;

COMMENT ON TABLE class_members IS 'Membership of students in classes; the basis for teacher read access.';

\echo === STEP 13: Table 9 of 40: domains ===
CREATE TABLE domains (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  section section_type NOT NULL,
  code varchar(50) NOT NULL,
  name varchar(120) NOT NULL,
  position smallint DEFAULT 0 NOT NULL,
  is_active boolean DEFAULT true NOT NULL,
  created_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_domains_code UNIQUE (code),
  CONSTRAINT uq_domains_id_section UNIQUE (id, section)
);

CREATE INDEX ix_domains_section_position ON domains USING btree (section, position);

COMMENT ON TABLE domains IS 'The 8 SAT domains (4 per section). Seed data.';

\echo === STEP 14: Table 10 of 40: skills ===
CREATE TABLE skills (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  domain_id uuid NOT NULL,
  section section_type NOT NULL,
  code varchar(80) NOT NULL,
  name varchar(200) NOT NULL,
  description text,
  position smallint DEFAULT 0 NOT NULL,
  is_active boolean DEFAULT true NOT NULL,
  created_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_skills_code UNIQUE (code),
  CONSTRAINT uq_skills_id_domain_section UNIQUE (id, domain_id, section),
  CONSTRAINT fk_skills_domain_section FOREIGN KEY (domain_id, section) REFERENCES domains(id, section)
);

CREATE INDEX ix_skills_domain_position ON skills USING btree (domain_id, position);

COMMENT ON TABLE skills IS 'The 29 testable skills. Each belongs to exactly one domain. Seed data.';

\echo === STEP 15: Table 11 of 40: passages ===
CREATE TABLE passages (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  content text NOT NULL,
  asset_key varchar(500),
  source varchar(200),
  status content_status DEFAULT 'draft' NOT NULL,
  created_by uuid,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_passages_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

COMMENT ON TABLE passages IS 'Shared reading stimulus (text and/or figure); one passage can serve several questions.';

\echo === STEP 16: Table 12 of 40: questions ===
CREATE TABLE questions (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  root_question_id uuid NOT NULL,
  revision integer DEFAULT 1 NOT NULL,
  supersedes_id uuid,
  section section_type NOT NULL,
  domain_id uuid NOT NULL,
  skill_id uuid NOT NULL,
  passage_id uuid,
  question_type question_type NOT NULL,
  stem text NOT NULL,
  stem_asset_key varchar(500),
  difficulty difficulty_level NOT NULL,
  calculator_allowed boolean DEFAULT true NOT NULL,
  irt_a real,
  irt_b real,
  irt_c real,
  source varchar(200),
  tags text[] DEFAULT '{}' NOT NULL,
  status content_status DEFAULT 'draft' NOT NULL,
  published_at timestamptz,
  created_by uuid,
  reviewed_by uuid,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_questions_root_question_id FOREIGN KEY (root_question_id) REFERENCES questions(id) ON DELETE RESTRICT,
  CONSTRAINT fk_questions_supersedes_id FOREIGN KEY (supersedes_id) REFERENCES questions(id) ON DELETE RESTRICT,
  CONSTRAINT fk_questions_domain_id FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE RESTRICT,
  CONSTRAINT fk_questions_passage_id FOREIGN KEY (passage_id) REFERENCES passages(id) ON DELETE RESTRICT,
  CONSTRAINT fk_questions_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
  CONSTRAINT fk_questions_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL,
  CONSTRAINT uq_questions_root_revision UNIQUE (root_question_id, revision),
  CONSTRAINT fk_questions_skill_category FOREIGN KEY (skill_id, domain_id, section) REFERENCES skills(id, domain_id, section),
  CONSTRAINT ck_questions_gridin_math CHECK (question_type <> 'grid_in' OR section = 'MATH'),
  CONSTRAINT ck_questions_passage_rw CHECK (passage_id IS NULL OR section = 'RW'),
  CONSTRAINT ck_questions_irt CHECK ((irt_a IS NULL OR irt_a > 0) AND (irt_c IS NULL OR irt_c BETWEEN 0 AND 1)),
  CONSTRAINT ck_questions_published_at CHECK (status <> 'published' OR published_at IS NOT NULL),
  CONSTRAINT ck_questions_revision CHECK (revision >= 1)
);

CREATE INDEX ix_questions_skill_difficulty ON questions USING btree (skill_id, difficulty) WHERE status = 'published';
CREATE INDEX ix_questions_domain_difficulty ON questions USING btree (domain_id, difficulty) WHERE status = 'published';
CREATE INDEX ix_questions_section_status ON questions USING btree (section, status);
CREATE INDEX ix_questions_passage ON questions USING btree (passage_id) WHERE passage_id IS NOT NULL;
CREATE INDEX ix_questions_root ON questions USING btree (root_question_id);
CREATE INDEX ix_questions_tags ON questions USING GIN (tags);

COMMENT ON TABLE questions IS 'The question bank. Published rows are immutable; edits create a new revision.';

\echo === STEP 17: Table 13 of 40: question_choices ===
CREATE TABLE question_choices (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  question_id uuid NOT NULL,
  label char(1) NOT NULL,
  content text NOT NULL,
  asset_key varchar(500),
  position smallint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_question_choices_question_id FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
  CONSTRAINT uq_choices_question_label UNIQUE (question_id, label),
  CONSTRAINT uq_choices_question_position UNIQUE (question_id, position),
  CONSTRAINT uq_choices_question_id_id UNIQUE (question_id, id),
  CONSTRAINT ck_choices_label CHECK (label IN ('A','B','C','D'))
);

COMMENT ON TABLE question_choices IS 'Answer options for multiple-choice questions. Contains NO correctness flag, so it is safe to serve.';

\echo === STEP 18: Table 14 of 40: grading.question_keys ===
CREATE TABLE grading.question_keys (
  question_id uuid NOT NULL,
  correct_choice_id uuid NOT NULL,
  PRIMARY KEY (question_id),
  CONSTRAINT fk_question_keys_question_id FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
  CONSTRAINT fk_keys_choice_belongs FOREIGN KEY (question_id, correct_choice_id) REFERENCES question_choices(question_id, id)
);

COMMENT ON TABLE grading.question_keys IS 'Correct choice per multiple-choice question. Lives in schema `grading`, unreadable by the serving role.';

\echo === STEP 19: Table 15 of 40: grading.spr_accepted_answers ===
CREATE TABLE grading.spr_accepted_answers (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  question_id uuid NOT NULL,
  raw_value varchar(30) NOT NULL,
  numeric_value numeric(20,10),
  PRIMARY KEY (id),
  CONSTRAINT fk_spr_accepted_answers_question_id FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
  CONSTRAINT uq_spr_question_value UNIQUE (question_id, raw_value),
  CONSTRAINT ck_spr_raw_format CHECK (raw_value ~ '^-?([0-9]+(\.[0-9]+)?|\.[0-9]+)(/[0-9]+)?$')
);

COMMENT ON TABLE grading.spr_accepted_answers IS 'All accepted forms for grid-in answers (e.g. 1/2, .5, 0.5). Lives in schema `grading`.';

\echo === STEP 20: Table 16 of 40: grading.question_explanations ===
CREATE TABLE grading.question_explanations (
  question_id uuid NOT NULL,
  explanation text NOT NULL,
  choice_rationales jsonb,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (question_id),
  CONSTRAINT fk_question_explanations_question_id FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

COMMENT ON TABLE grading.question_explanations IS 'Explanation and per-choice rationale. Revealed only after the module is submitted. Lives in schema `grading`.';

\echo === STEP 21: Table 17 of 40: tests ===
CREATE TABLE tests (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  slug varchar(120) NOT NULL,
  title varchar(200) NOT NULL,
  description text,
  test_type test_type DEFAULT 'full_mock' NOT NULL,
  is_adaptive boolean DEFAULT true NOT NULL,
  content_version integer DEFAULT 1 NOT NULL,
  status content_status DEFAULT 'draft' NOT NULL,
  published_at timestamptz,
  source varchar(200),
  created_by uuid,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_tests_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
  CONSTRAINT uq_tests_slug UNIQUE (slug),
  CONSTRAINT ck_tests_published_at CHECK (status <> 'published' OR published_at IS NOT NULL)
);

CREATE INDEX ix_tests_published ON tests USING btree (test_type, published_at DESC) WHERE status = 'published';

COMMENT ON TABLE tests IS 'A deliverable test: full mock, section practice, or skill practice.';

\echo === STEP 22: Table 18 of 40: test_sections ===
CREATE TABLE test_sections (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  test_id uuid NOT NULL,
  section section_type NOT NULL,
  position smallint NOT NULL,
  break_seconds integer,
  break_skippable boolean DEFAULT true NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_test_sections_test_id FOREIGN KEY (test_id) REFERENCES tests(id) ON DELETE CASCADE,
  CONSTRAINT uq_sections_test_section UNIQUE (test_id, section),
  CONSTRAINT uq_sections_test_position UNIQUE (test_id, position),
  CONSTRAINT ck_sections_break CHECK (break_seconds IS NULL OR break_seconds BETWEEN 0 AND 3600)
);

COMMENT ON TABLE test_sections IS 'Reading & Writing and Math sections of a test, with the break that follows each.';

\echo === STEP 23: Table 19 of 40: test_modules ===
CREATE TABLE test_modules (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  section_id uuid NOT NULL,
  stage smallint NOT NULL,
  level module_level NOT NULL,
  time_limit_sec integer NOT NULL,
  question_target smallint NOT NULL,
  routing_threshold numeric(4,3),
  routing_weight_easy smallint,
  routing_weight_medium smallint,
  routing_weight_hard smallint,
  PRIMARY KEY (id),
  CONSTRAINT fk_test_modules_section_id FOREIGN KEY (section_id) REFERENCES test_sections(id) ON DELETE CASCADE,
  CONSTRAINT uq_modules_slot UNIQUE (section_id, stage, level),
  CONSTRAINT ck_modules_stage_level CHECK ((stage = 1 AND level = 'router') OR (stage = 2 AND level IN ('easy','hard'))),
  CONSTRAINT ck_modules_time CHECK (time_limit_sec BETWEEN 60 AND 14400),
  CONSTRAINT ck_modules_question_target CHECK (question_target BETWEEN 1 AND 100),
  CONSTRAINT ck_modules_routing_stage1_only CHECK (stage = 1 OR (routing_threshold IS NULL AND routing_weight_easy IS NULL AND routing_weight_medium IS NULL AND routing_weight_hard IS NULL)),
  CONSTRAINT ck_modules_routing_values CHECK ((routing_threshold IS NULL OR routing_threshold BETWEEN 0 AND 1) AND COALESCE(routing_weight_easy,1) > 0 AND COALESCE(routing_weight_medium,1) > 0 AND COALESCE(routing_weight_hard,1) > 0)
);

COMMENT ON TABLE test_modules IS 'Module slots: stage 1 (router) and stage 2 (easy / hard) per section.';

\echo === STEP 24: Table 20 of 40: module_blueprints ===
CREATE TABLE module_blueprints (
  module_id uuid NOT NULL,
  domain_id uuid NOT NULL,
  question_count smallint NOT NULL,
  easy_count smallint DEFAULT 0 NOT NULL,
  medium_count smallint DEFAULT 0 NOT NULL,
  hard_count smallint DEFAULT 0 NOT NULL,
  PRIMARY KEY (module_id, domain_id),
  CONSTRAINT fk_module_blueprints_module_id FOREIGN KEY (module_id) REFERENCES test_modules(id) ON DELETE CASCADE,
  CONSTRAINT fk_module_blueprints_domain_id FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE RESTRICT,
  CONSTRAINT ck_blueprint_sum CHECK (easy_count + medium_count + hard_count = question_count),
  CONSTRAINT ck_blueprint_nonneg CHECK (question_count >= 0 AND easy_count >= 0 AND medium_count >= 0 AND hard_count >= 0)
);

CREATE INDEX ix_blueprints_domain ON module_blueprints USING btree (domain_id);

COMMENT ON TABLE module_blueprints IS 'How many questions of each domain and difficulty a module must contain.';

\echo === STEP 25: Table 21 of 40: module_questions ===
CREATE TABLE module_questions (
  module_id uuid NOT NULL,
  question_id uuid NOT NULL,
  position smallint NOT NULL,
  PRIMARY KEY (module_id, question_id),
  CONSTRAINT fk_module_questions_module_id FOREIGN KEY (module_id) REFERENCES test_modules(id) ON DELETE CASCADE,
  CONSTRAINT fk_module_questions_question_id FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE RESTRICT,
  CONSTRAINT uq_module_questions_position UNIQUE (module_id, position),
  CONSTRAINT ck_module_questions_position CHECK (position >= 1)
);

CREATE INDEX ix_module_questions_question ON module_questions USING btree (question_id);

COMMENT ON TABLE module_questions IS 'Ordered list of questions in a module.';

\echo === STEP 26: Table 22 of 40: score_conversions ===
CREATE TABLE score_conversions (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  test_id uuid NOT NULL,
  section section_type NOT NULL,
  stage2_level module_level NOT NULL,
  raw_score smallint NOT NULL,
  scaled_score smallint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_score_conversions_test_id FOREIGN KEY (test_id) REFERENCES tests(id) ON DELETE CASCADE,
  CONSTRAINT uq_score_conv UNIQUE (test_id, section, stage2_level, raw_score),
  CONSTRAINT ck_score_conv_range CHECK (scaled_score BETWEEN 200 AND 800 AND raw_score >= 0 AND stage2_level IN ('easy','hard'))
);

COMMENT ON TABLE score_conversions IS 'Raw-to-scaled score lookup per test, section and stage-2 path.';

\echo === STEP 27: Table 23 of 40: test_attempts ===
CREATE TABLE test_attempts (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  user_id uuid NOT NULL,
  test_id uuid NOT NULL,
  test_content_version integer NOT NULL,
  status attempt_status DEFAULT 'in_progress' NOT NULL,
  time_multiplier numeric(3,2) DEFAULT 1.00 NOT NULL,
  started_at timestamptz DEFAULT now() NOT NULL,
  completed_at timestamptz,
  last_activity_at timestamptz DEFAULT now() NOT NULL,
  voided_reason varchar(200),
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_test_attempts_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_test_attempts_test_id FOREIGN KEY (test_id) REFERENCES tests(id) ON DELETE RESTRICT,
  CONSTRAINT uq_attempts_id_user UNIQUE (id, user_id),
  CONSTRAINT ck_attempts_completed CHECK ((status = 'completed') = (completed_at IS NOT NULL)),
  CONSTRAINT ck_attempts_time CHECK (completed_at IS NULL OR completed_at >= started_at),
  CONSTRAINT ck_attempts_multiplier CHECK (time_multiplier BETWEEN 1.00 AND 3.00)
);

CREATE UNIQUE INDEX uq_attempts_one_active ON test_attempts (user_id, test_id) WHERE status = 'in_progress';
CREATE INDEX ix_attempts_user_started ON test_attempts USING btree (user_id, started_at DESC);
CREATE INDEX ix_attempts_active_activity ON test_attempts USING btree (last_activity_at) WHERE status = 'in_progress';
CREATE INDEX ix_attempts_test ON test_attempts USING btree (test_id);

COMMENT ON TABLE test_attempts IS 'One student sitting one test from start to finish.';

\echo === STEP 28: Table 24 of 40: module_attempts ===
CREATE TABLE module_attempts (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  attempt_id uuid NOT NULL,
  user_id uuid NOT NULL,
  module_id uuid NOT NULL,
  sequence smallint NOT NULL,
  status module_attempt_status DEFAULT 'not_started' NOT NULL,
  started_at timestamptz,
  deadline_at timestamptz,
  submitted_at timestamptz,
  submit_reason submit_reason,
  question_count smallint,
  correct_count smallint,
  weighted_score numeric(6,4),
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_module_attempts_module_id FOREIGN KEY (module_id) REFERENCES test_modules(id) ON DELETE RESTRICT,
  CONSTRAINT fk_module_attempts_attempt_user FOREIGN KEY (attempt_id, user_id) REFERENCES test_attempts(id, user_id) ON DELETE CASCADE,
  CONSTRAINT uq_module_attempts_attempt_module UNIQUE (attempt_id, module_id),
  CONSTRAINT uq_module_attempts_attempt_seq UNIQUE (attempt_id, sequence),
  CONSTRAINT uq_module_attempts_id_user UNIQUE (id, user_id),
  CONSTRAINT ck_module_attempts_state CHECK ((status='not_started' AND started_at IS NULL) OR (status='in_progress' AND started_at IS NOT NULL AND deadline_at IS NOT NULL) OR (status='submitted' AND started_at IS NOT NULL AND submitted_at IS NOT NULL AND submit_reason IS NOT NULL)),
  CONSTRAINT ck_module_attempts_deadline CHECK (deadline_at IS NULL OR deadline_at > started_at),
  CONSTRAINT ck_module_attempts_counts CHECK (correct_count IS NULL OR (question_count IS NOT NULL AND correct_count BETWEEN 0 AND question_count))
)
WITH (fillfactor = 85);

CREATE UNIQUE INDEX uq_module_attempts_one_open ON module_attempts (attempt_id) WHERE status = 'in_progress';
CREATE INDEX ix_module_attempts_deadline ON module_attempts USING btree (deadline_at) WHERE status = 'in_progress';
CREATE INDEX ix_module_attempts_user ON module_attempts USING btree (user_id, created_at DESC);
CREATE INDEX ix_module_attempts_module ON module_attempts USING btree (module_id);

COMMENT ON TABLE module_attempts IS 'One student''s pass through one module. Holds the server-authoritative timer.';

\echo === STEP 29: Table 25 of 40: routing_decisions ===
CREATE TABLE routing_decisions (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  from_module_attempt_id uuid NOT NULL,
  to_module_id uuid NOT NULL,
  score numeric(6,4) NOT NULL,
  threshold numeric(4,3) NOT NULL,
  chosen_level module_level NOT NULL,
  algorithm_version varchar(20) NOT NULL,
  decided_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_routing_decisions_from_module_attempt_id FOREIGN KEY (from_module_attempt_id) REFERENCES module_attempts(id) ON DELETE CASCADE,
  CONSTRAINT fk_routing_decisions_to_module_id FOREIGN KEY (to_module_id) REFERENCES test_modules(id) ON DELETE RESTRICT,
  CONSTRAINT uq_routing_from UNIQUE (from_module_attempt_id),
  CONSTRAINT ck_routing_values CHECK (score BETWEEN 0 AND 1 AND threshold BETWEEN 0 AND 1 AND chosen_level IN ('easy','hard'))
);

CREATE INDEX ix_routing_to_module ON routing_decisions USING btree (to_module_id);

COMMENT ON TABLE routing_decisions IS 'Audit record of why a student received the easy or hard stage-2 module.';

\echo === STEP 30: Table 26 of 40: break_sessions ===
CREATE TABLE break_sessions (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  attempt_id uuid NOT NULL,
  user_id uuid NOT NULL,
  after_section_id uuid NOT NULL,
  started_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  skipped_at timestamptz,
  PRIMARY KEY (id),
  CONSTRAINT fk_break_sessions_after_section_id FOREIGN KEY (after_section_id) REFERENCES test_sections(id) ON DELETE RESTRICT,
  CONSTRAINT fk_break_attempt_user FOREIGN KEY (attempt_id, user_id) REFERENCES test_attempts(id, user_id) ON DELETE CASCADE,
  CONSTRAINT uq_break_once UNIQUE (attempt_id, after_section_id),
  CONSTRAINT ck_break_window CHECK (ends_at > started_at AND (skipped_at IS NULL OR skipped_at BETWEEN started_at AND ends_at))
);

CREATE INDEX ix_break_user ON break_sessions USING btree (user_id);

COMMENT ON TABLE break_sessions IS 'The 10-minute break between sections, with skip tracking.';

\echo === STEP 31: Table 27 of 40: answers ===
CREATE TABLE answers (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  module_attempt_id uuid NOT NULL,
  question_id uuid NOT NULL,
  user_id uuid NOT NULL,
  section section_type NOT NULL,
  domain_id uuid NOT NULL,
  skill_id uuid NOT NULL,
  difficulty difficulty_level NOT NULL,
  selected_choice_id uuid,
  response_text varchar(30),
  eliminated_choice_ids uuid[] DEFAULT '{}' NOT NULL,
  is_flagged boolean DEFAULT false NOT NULL,
  is_correct boolean,
  time_spent_ms integer DEFAULT 0 NOT NULL,
  visit_count smallint DEFAULT 0 NOT NULL,
  first_answered_at timestamptz,
  revision integer DEFAULT 0 NOT NULL,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_answers_question_id FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE RESTRICT,
  CONSTRAINT fk_answers_attempt_user FOREIGN KEY (module_attempt_id, user_id) REFERENCES module_attempts(id, user_id) ON DELETE CASCADE,
  CONSTRAINT uq_answers_attempt_question UNIQUE (module_attempt_id, question_id),
  CONSTRAINT fk_answers_choice_belongs FOREIGN KEY (question_id, selected_choice_id) REFERENCES question_choices(question_id, id),
  CONSTRAINT ck_answers_one_kind CHECK (NOT (selected_choice_id IS NOT NULL AND response_text IS NOT NULL)),
  CONSTRAINT ck_answers_time CHECK (time_spent_ms BETWEEN 0 AND 7200000 AND visit_count >= 0),
  CONSTRAINT ck_answers_eliminated CHECK (cardinality(eliminated_choice_ids) <= 3),
  CONSTRAINT ck_answers_response_text CHECK (response_text IS NULL OR response_text ~ '^-?([0-9]+(\.[0-9]+)?|\.[0-9]+)(/[0-9]+)?$')
)
WITH (fillfactor = 85);

CREATE INDEX ix_answers_user_skill ON answers USING btree (user_id, skill_id) INCLUDE (is_correct, time_spent_ms);
CREATE INDEX ix_answers_user_domain ON answers USING btree (user_id, domain_id) INCLUDE (is_correct);
CREATE INDEX ix_answers_question ON answers USING btree (question_id) INCLUDE (is_correct);
CREATE INDEX ix_answers_created_brin ON answers USING BRIN (created_at);

COMMENT ON TABLE answers IS 'Current state of one question inside one module attempt. Upserted on every autosave.';

\echo === STEP 32: Table 28 of 40: answer_events ===
CREATE TABLE answer_events (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  server_ts timestamptz DEFAULT now() NOT NULL,
  module_attempt_id uuid NOT NULL,
  question_id uuid NOT NULL,
  event_type answer_event_type NOT NULL,
  payload jsonb,
  client_ts timestamptz,
  PRIMARY KEY (id, server_ts),
  CONSTRAINT fk_answer_events_module_attempt_id FOREIGN KEY (module_attempt_id) REFERENCES module_attempts(id) ON DELETE CASCADE
)
PARTITION BY RANGE (server_ts);

CREATE INDEX ix_answer_events_attempt ON answer_events USING btree (module_attempt_id, server_ts);

COMMENT ON TABLE answer_events IS 'Append-only interaction log: select, clear, flag, eliminate, visit. For audit and timing analysis.';

\echo === STEP 33: Table 29 of 40: annotations ===
CREATE TABLE annotations (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  module_attempt_id uuid NOT NULL,
  user_id uuid NOT NULL,
  question_id uuid NOT NULL,
  target varchar(10) DEFAULT 'passage' NOT NULL,
  start_offset integer NOT NULL,
  end_offset integer NOT NULL,
  color varchar(16) DEFAULT 'yellow' NOT NULL,
  note text,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_annotations_question_id FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE RESTRICT,
  CONSTRAINT fk_annotations_attempt_user FOREIGN KEY (module_attempt_id, user_id) REFERENCES module_attempts(id, user_id) ON DELETE CASCADE,
  CONSTRAINT ck_annotations_range CHECK (start_offset >= 0 AND end_offset > start_offset),
  CONSTRAINT ck_annotations_values CHECK (target IN ('passage','stem') AND color IN ('yellow','blue','pink') AND (note IS NULL OR char_length(note) <= 2000))
);

CREATE INDEX ix_annotations_attempt_question ON annotations USING btree (module_attempt_id, question_id);
CREATE INDEX ix_annotations_user ON annotations USING btree (user_id);

COMMENT ON TABLE annotations IS 'Highlights and notes on passages and stems (Bluebook highlight & notes).';

\echo === STEP 34: Table 30 of 40: score_reports ===
CREATE TABLE score_reports (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  attempt_id uuid NOT NULL,
  user_id uuid NOT NULL,
  rw_raw smallint,
  math_raw smallint,
  rw_scaled smallint,
  math_scaled smallint,
  total_scaled smallint,
  rw_theta real,
  math_theta real,
  rw_stage2_level module_level,
  math_stage2_level module_level,
  scoring_version varchar(20) NOT NULL,
  generated_at timestamptz DEFAULT now() NOT NULL,
  created_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_score_reports_attempt_user FOREIGN KEY (attempt_id, user_id) REFERENCES test_attempts(id, user_id) ON DELETE CASCADE,
  CONSTRAINT uq_score_reports_attempt UNIQUE (attempt_id),
  CONSTRAINT ck_score_ranges CHECK ((rw_scaled IS NULL OR rw_scaled BETWEEN 200 AND 800) AND (math_scaled IS NULL OR math_scaled BETWEEN 200 AND 800) AND (total_scaled IS NULL OR total_scaled BETWEEN 400 AND 1600)),
  CONSTRAINT ck_score_total_sum CHECK (total_scaled IS NULL OR total_scaled = rw_scaled + math_scaled)
);

CREATE INDEX ix_score_reports_user ON score_reports USING btree (user_id, generated_at DESC);

COMMENT ON TABLE score_reports IS 'Final scores for a completed attempt. Derived; rebuildable from answers.';

\echo === STEP 35: Table 31 of 40: domain_results ===
CREATE TABLE domain_results (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  report_id uuid NOT NULL,
  domain_id uuid NOT NULL,
  total smallint NOT NULL,
  correct smallint NOT NULL,
  unanswered smallint DEFAULT 0 NOT NULL,
  accuracy numeric(5,2) NOT NULL,
  avg_time_ms integer,
  PRIMARY KEY (id),
  CONSTRAINT fk_domain_results_report_id FOREIGN KEY (report_id) REFERENCES score_reports(id) ON DELETE CASCADE,
  CONSTRAINT fk_domain_results_domain_id FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE RESTRICT,
  CONSTRAINT uq_domain_results UNIQUE (report_id, domain_id),
  CONSTRAINT ck_domain_results_counts CHECK (correct >= 0 AND unanswered >= 0 AND correct + unanswered <= total AND accuracy BETWEEN 0 AND 100)
);

COMMENT ON TABLE domain_results IS 'Per-attempt performance by domain. Derived.';

\echo === STEP 36: Table 32 of 40: skill_results ===
CREATE TABLE skill_results (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  report_id uuid NOT NULL,
  skill_id uuid NOT NULL,
  domain_id uuid NOT NULL,
  total smallint NOT NULL,
  correct smallint NOT NULL,
  unanswered smallint DEFAULT 0 NOT NULL,
  accuracy numeric(5,2) NOT NULL,
  avg_time_ms integer,
  easy_total smallint DEFAULT 0 NOT NULL,
  easy_correct smallint DEFAULT 0 NOT NULL,
  medium_total smallint DEFAULT 0 NOT NULL,
  medium_correct smallint DEFAULT 0 NOT NULL,
  hard_total smallint DEFAULT 0 NOT NULL,
  hard_correct smallint DEFAULT 0 NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_skill_results_report_id FOREIGN KEY (report_id) REFERENCES score_reports(id) ON DELETE CASCADE,
  CONSTRAINT fk_skill_results_skill_id FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE RESTRICT,
  CONSTRAINT uq_skill_results UNIQUE (report_id, skill_id),
  CONSTRAINT ck_skill_results_counts CHECK (correct >= 0 AND unanswered >= 0 AND correct + unanswered <= total AND accuracy BETWEEN 0 AND 100),
  CONSTRAINT ck_skill_results_difficulty CHECK (easy_total + medium_total + hard_total = total AND easy_correct <= easy_total AND medium_correct <= medium_total AND hard_correct <= hard_total)
);

CREATE INDEX ix_skill_results_skill ON skill_results USING btree (skill_id);

COMMENT ON TABLE skill_results IS 'Per-attempt performance by skill, split by difficulty. Derived; the core weakness breakdown for one test.';

\echo === STEP 37: Table 33 of 40: user_skill_stats ===
CREATE TABLE user_skill_stats (
  user_id uuid NOT NULL,
  skill_id uuid NOT NULL,
  total_answered integer DEFAULT 0 NOT NULL,
  total_correct integer DEFAULT 0 NOT NULL,
  accuracy_pct numeric(5,2) GENERATED ALWAYS AS (CASE WHEN total_answered = 0 THEN NULL ELSE round(100.0 * total_correct / total_answered, 2) END) STORED,
  recent_accuracy numeric(5,2),
  recent_window smallint DEFAULT 20 NOT NULL,
  mastery numeric(5,4),
  avg_time_ms integer,
  last_practiced_at timestamptz,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (user_id, skill_id),
  CONSTRAINT fk_user_skill_stats_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_user_skill_stats_skill_id FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
  CONSTRAINT ck_uss_counts CHECK (total_correct BETWEEN 0 AND total_answered AND (mastery IS NULL OR mastery BETWEEN 0 AND 1))
);

CREATE INDEX ix_uss_user_accuracy ON user_skill_stats USING btree (user_id, accuracy_pct ASC NULLS LAST);
CREATE INDEX ix_uss_skill ON user_skill_stats USING btree (skill_id);

COMMENT ON TABLE user_skill_stats IS 'Rolling lifetime per-student per-skill aggregate. The long-term weakness profile (max 29 rows per student).';

\echo === STEP 38: Table 34 of 40: user_domain_stats ===
CREATE TABLE user_domain_stats (
  user_id uuid NOT NULL,
  domain_id uuid NOT NULL,
  total_answered integer DEFAULT 0 NOT NULL,
  total_correct integer DEFAULT 0 NOT NULL,
  accuracy_pct numeric(5,2) GENERATED ALWAYS AS (CASE WHEN total_answered = 0 THEN NULL ELSE round(100.0 * total_correct / total_answered, 2) END) STORED,
  mastery numeric(5,4),
  avg_time_ms integer,
  last_practiced_at timestamptz,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (user_id, domain_id),
  CONSTRAINT fk_user_domain_stats_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_user_domain_stats_domain_id FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE,
  CONSTRAINT ck_uds_counts CHECK (total_correct BETWEEN 0 AND total_answered AND (mastery IS NULL OR mastery BETWEEN 0 AND 1))
);

CREATE INDEX ix_uds_user_accuracy ON user_domain_stats USING btree (user_id, accuracy_pct ASC NULLS LAST);

COMMENT ON TABLE user_domain_stats IS 'Same as user_skill_stats at domain level (max 8 rows per student).';

\echo === STEP 39: Table 35 of 40: user_stats ===
CREATE TABLE user_stats (
  user_id uuid NOT NULL,
  attempts_completed integer DEFAULT 0 NOT NULL,
  questions_answered integer DEFAULT 0 NOT NULL,
  questions_correct integer DEFAULT 0 NOT NULL,
  overall_accuracy numeric(5,2) GENERATED ALWAYS AS (CASE WHEN questions_answered = 0 THEN NULL ELSE round(100.0 * questions_correct / questions_answered, 2) END) STORED,
  best_total_score smallint,
  latest_total_score smallint,
  last_attempt_at timestamptz,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (user_id),
  CONSTRAINT fk_user_stats_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT ck_user_stats_counts CHECK (questions_correct BETWEEN 0 AND questions_answered)
);

COMMENT ON TABLE user_stats IS 'Overall per-student summary for the dashboard header.';

\echo === STEP 40: Table 36 of 40: question_stats ===
CREATE TABLE question_stats (
  question_id uuid NOT NULL,
  times_served integer DEFAULT 0 NOT NULL,
  times_answered integer DEFAULT 0 NOT NULL,
  times_correct integer DEFAULT 0 NOT NULL,
  accuracy_pct numeric(5,2) GENERATED ALWAYS AS (CASE WHEN times_answered = 0 THEN NULL ELSE round(100.0 * times_correct / times_answered, 2) END) STORED,
  avg_time_ms integer,
  choice_distribution jsonb,
  last_calibrated_at timestamptz,
  processed_through timestamptz,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (question_id),
  CONSTRAINT fk_question_stats_question_id FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
  CONSTRAINT ck_question_stats_counts CHECK (times_correct BETWEEN 0 AND times_answered AND times_answered <= times_served)
);

CREATE INDEX ix_question_stats_quality ON question_stats USING btree (accuracy_pct) WHERE times_answered >= 100;

COMMENT ON TABLE question_stats IS 'Global per-question statistics for quality control and IRT calibration. Updated in batches.';

\echo === STEP 41: Table 37 of 40: user_goals ===
CREATE TABLE user_goals (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  user_id uuid NOT NULL,
  skill_id uuid,
  target_accuracy numeric(5,2),
  target_score smallint,
  target_date date,
  achieved_at timestamptz,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_user_goals_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_user_goals_skill_id FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
  CONSTRAINT uq_goals_user_skill UNIQUE NULLS NOT DISTINCT (user_id, skill_id),
  CONSTRAINT ck_goals_values CHECK ((target_accuracy IS NOT NULL OR target_score IS NOT NULL) AND (target_accuracy IS NULL OR target_accuracy BETWEEN 0 AND 100) AND (target_score IS NULL OR target_score BETWEEN 400 AND 1600))
);

COMMENT ON TABLE user_goals IS 'Per-student targets: overall (skill_id NULL) or per skill.';

\echo === STEP 42: Table 38 of 40: audit_logs ===
CREATE TABLE audit_logs (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  created_at timestamptz DEFAULT now() NOT NULL,
  actor_user_id uuid,
  action varchar(60) NOT NULL,
  entity_type varchar(60) NOT NULL,
  entity_id uuid,
  before_data jsonb,
  after_data jsonb,
  ip inet,
  request_id uuid,
  PRIMARY KEY (id, created_at),
  CONSTRAINT fk_audit_logs_actor_user_id FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL
)
PARTITION BY RANGE (created_at);

CREATE INDEX ix_audit_entity ON audit_logs USING btree (entity_type, entity_id, created_at DESC);
CREATE INDEX ix_audit_actor ON audit_logs USING btree (actor_user_id, created_at DESC);

COMMENT ON TABLE audit_logs IS 'Append-only record of admin and privileged actions (content edits, role changes, voiding attempts).';

\echo === STEP 43: Table 39 of 40: data_requests ===
CREATE TABLE data_requests (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  user_id uuid,
  request_type data_request_type NOT NULL,
  status data_request_status DEFAULT 'pending' NOT NULL,
  requested_at timestamptz DEFAULT now() NOT NULL,
  completed_at timestamptz,
  export_asset_key varchar(500),
  expires_at timestamptz,
  failure_reason text,
  PRIMARY KEY (id),
  CONSTRAINT fk_data_requests_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
  CONSTRAINT ck_data_requests_done CHECK (status <> 'completed' OR completed_at IS NOT NULL)
);

CREATE INDEX ix_data_requests_open ON data_requests USING btree (status, requested_at) WHERE status IN ('pending','processing');

COMMENT ON TABLE data_requests IS 'GDPR / privacy export and deletion requests and their fulfilment status.';

\echo === STEP 44: Table 40 of 40: idempotency_keys ===
CREATE TABLE idempotency_keys (
  user_id uuid NOT NULL,
  idem_key varchar(80) NOT NULL,
  endpoint varchar(100) NOT NULL,
  request_hash char(64) NOT NULL,
  response_status smallint,
  response_body jsonb,
  created_at timestamptz DEFAULT now() NOT NULL,
  expires_at timestamptz DEFAULT now() + interval '24 hours' NOT NULL,
  PRIMARY KEY (user_id, idem_key),
  CONSTRAINT fk_idempotency_keys_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT ck_idem_expiry CHECK (expires_at > created_at)
);

CREATE INDEX ix_idem_expires ON idempotency_keys USING btree (expires_at);

COMMENT ON TABLE idempotency_keys IS 'Prevents double-submit of module submit, start and break endpoints on retries.';

\echo === STEP 45: Create default and monthly partitions ===
-- default partitions catch any row outside the created months (so inserts never fail)
CREATE TABLE auth_events_default   PARTITION OF auth_events   DEFAULT;
CREATE TABLE audit_logs_default    PARTITION OF audit_logs    DEFAULT;
CREATE TABLE answer_events_default PARTITION OF answer_events DEFAULT;

-- one month back, current month and 3 months ahead
SELECT create_monthly_partitions('auth_events',   1, 3);
SELECT create_monthly_partitions('audit_logs',    1, 3);
SELECT create_monthly_partitions('answer_events', 1, 3);

\echo === STEP 46: Trigger: keep updated_at correct on every table ===
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON classes
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON passages
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON questions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON grading.question_explanations
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON tests
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON test_attempts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON module_attempts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON answers
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON annotations
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON user_skill_stats
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON user_domain_stats
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON user_stats
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON question_stats
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON user_goals
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

\echo === STEP 47: Trigger: published questions and passages are immutable ===
CREATE FUNCTION trg_lock_published_question() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'published' THEN
      RAISE EXCEPTION 'Published question % cannot be deleted; archive it instead', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'archived' AND NEW.status <> 'archived' THEN
    RAISE EXCEPTION 'Archived question % cannot be reopened; create a new revision', OLD.id USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'published' THEN
    IF NEW.status NOT IN ('published', 'archived') THEN
      RAISE EXCEPTION 'Published question % can only be archived', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    IF (NEW.stem, NEW.stem_asset_key, NEW.difficulty, NEW.skill_id, NEW.domain_id, NEW.section, NEW.passage_id,
        NEW.question_type, NEW.calculator_allowed, NEW.root_question_id, NEW.revision, NEW.supersedes_id)
       IS DISTINCT FROM
       (OLD.stem, OLD.stem_asset_key, OLD.difficulty, OLD.skill_id, OLD.domain_id, OLD.section, OLD.passage_id,
        OLD.question_type, OLD.calculator_allowed, OLD.root_question_id, OLD.revision, OLD.supersedes_id) THEN
      RAISE EXCEPTION 'Published question % is immutable; create a new revision', OLD.id USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_lock_published_question
  BEFORE UPDATE OR DELETE ON questions
  FOR EACH ROW EXECUTE FUNCTION trg_lock_published_question();

-- children of a question: choices, keys, accepted answers, explanations
CREATE FUNCTION trg_lock_published_question_child() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  qids uuid[]; st content_status; q uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    qids := ARRAY[OLD.question_id];
  ELSIF TG_OP = 'INSERT' THEN
    qids := ARRAY[NEW.question_id];
  ELSE
    qids := ARRAY[OLD.question_id, NEW.question_id];
  END IF;
  FOREACH q IN ARRAY qids LOOP
    SELECT status INTO st FROM questions WHERE id = q;
    IF st = 'published' THEN
      RAISE EXCEPTION 'Question % is published; its % rows are immutable (create a new revision)', q, TG_TABLE_NAME
        USING ERRCODE = 'check_violation';
    END IF;
  END LOOP;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_lock_published_child BEFORE INSERT OR UPDATE OR DELETE ON question_choices
  FOR EACH ROW EXECUTE FUNCTION trg_lock_published_question_child();
CREATE TRIGGER trg_lock_published_child BEFORE INSERT OR UPDATE OR DELETE ON grading.question_keys
  FOR EACH ROW EXECUTE FUNCTION trg_lock_published_question_child();
CREATE TRIGGER trg_lock_published_child BEFORE INSERT OR UPDATE OR DELETE ON grading.spr_accepted_answers
  FOR EACH ROW EXECUTE FUNCTION trg_lock_published_question_child();
CREATE TRIGGER trg_lock_published_child BEFORE INSERT OR UPDATE OR DELETE ON grading.question_explanations
  FOR EACH ROW EXECUTE FUNCTION trg_lock_published_question_child();

-- passages
CREATE FUNCTION trg_lock_published_passage() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'published' THEN
      RAISE EXCEPTION 'Published passage % cannot be deleted', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'published' AND
     (NEW.content, NEW.asset_key) IS DISTINCT FROM (OLD.content, OLD.asset_key) THEN
    RAISE EXCEPTION 'Published passage % is immutable', OLD.id USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_lock_published_passage BEFORE UPDATE OR DELETE ON passages
  FOR EACH ROW EXECUTE FUNCTION trg_lock_published_passage();

\echo === STEP 48: Trigger: a question cannot go live without a complete answer key ===
CREATE FUNCTION ctrg_question_key_complete() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, grading, pg_temp AS $$
DECLARE n int;
BEGIN
  IF NEW.question_type = 'multiple_choice' THEN
    SELECT count(*) INTO n FROM question_choices WHERE question_id = NEW.id;
    IF n <> 4 THEN
      RAISE EXCEPTION 'Question % needs exactly 4 choices before publishing (has %)', NEW.id, n USING ERRCODE = 'check_violation';
    END IF;
    SELECT count(*) INTO n FROM grading.question_keys WHERE question_id = NEW.id;
    IF n <> 1 THEN
      RAISE EXCEPTION 'Question % needs exactly 1 answer key before publishing', NEW.id USING ERRCODE = 'check_violation';
    END IF;
  ELSE
    SELECT count(*) INTO n FROM grading.spr_accepted_answers WHERE question_id = NEW.id;
    IF n < 1 THEN
      RAISE EXCEPTION 'Grid-in question % needs at least 1 accepted answer before publishing', NEW.id USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM grading.question_explanations WHERE question_id = NEW.id) THEN
    RAISE EXCEPTION 'Question % needs an explanation before publishing', NEW.id USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER ctrg_question_key_complete_ins AFTER INSERT ON questions
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.status = 'published')
  EXECUTE FUNCTION ctrg_question_key_complete();
CREATE CONSTRAINT TRIGGER ctrg_question_key_complete_upd AFTER UPDATE OF status ON questions
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.status = 'published' AND OLD.status IS DISTINCT FROM 'published')
  EXECUTE FUNCTION ctrg_question_key_complete();

\echo === STEP 49: Trigger: published tests are immutable ===
CREATE FUNCTION trg_lock_published_test() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'published' THEN
      RAISE EXCEPTION 'Published test % cannot be deleted; archive it', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'published' THEN
    IF NEW.status NOT IN ('published', 'archived') THEN
      RAISE EXCEPTION 'Published test % can only be archived', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    IF (NEW.test_type, NEW.is_adaptive, NEW.content_version, NEW.slug)
       IS DISTINCT FROM (OLD.test_type, OLD.is_adaptive, OLD.content_version, OLD.slug) THEN
      RAISE EXCEPTION 'Published test % structure is immutable; clone to a new content_version', OLD.id USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_lock_published_test BEFORE UPDATE OR DELETE ON tests
  FOR EACH ROW EXECUTE FUNCTION trg_lock_published_test();

-- children: sections, modules, blueprints, module_questions
CREATE FUNCTION trg_lock_published_test_child() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE r record; tid uuid; st content_status; j jsonb;
BEGIN
  IF TG_OP = 'DELETE' THEN r := OLD; ELSE r := NEW; END IF;
  j := to_jsonb(r);
  IF TG_TABLE_NAME = 'test_sections' THEN
    tid := (j->>'test_id')::uuid;
  ELSIF TG_TABLE_NAME = 'test_modules' THEN
    SELECT ts.test_id INTO tid FROM test_sections ts WHERE ts.id = (j->>'section_id')::uuid;
  ELSE
    SELECT ts.test_id INTO tid FROM test_modules tm JOIN test_sections ts ON ts.id = tm.section_id
      WHERE tm.id = (j->>'module_id')::uuid;
  END IF;
  SELECT status INTO st FROM tests WHERE id = tid;
  IF st = 'published' THEN
    RAISE EXCEPTION 'Test % is published; % cannot change (clone to a new content_version)', tid, TG_TABLE_NAME
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN r;
END $$;

CREATE TRIGGER trg_lock_published_child BEFORE INSERT OR UPDATE OR DELETE ON test_sections
  FOR EACH ROW EXECUTE FUNCTION trg_lock_published_test_child();
CREATE TRIGGER trg_lock_published_child BEFORE INSERT OR UPDATE OR DELETE ON test_modules
  FOR EACH ROW EXECUTE FUNCTION trg_lock_published_test_child();
CREATE TRIGGER trg_lock_published_child BEFORE INSERT OR UPDATE OR DELETE ON module_blueprints
  FOR EACH ROW EXECUTE FUNCTION trg_lock_published_test_child();
CREATE TRIGGER trg_lock_published_child BEFORE INSERT OR UPDATE OR DELETE ON module_questions
  FOR EACH ROW EXECUTE FUNCTION trg_lock_published_test_child();

\echo === STEP 50: Trigger: modules only accept matching published questions ===
CREATE FUNCTION trg_validate_module_question() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE qs content_status; qsec section_type; msec section_type;
BEGIN
  SELECT status, section INTO qs, qsec FROM questions WHERE id = NEW.question_id;
  SELECT ts.section INTO msec FROM test_modules tm JOIN test_sections ts ON ts.id = tm.section_id
    WHERE tm.id = NEW.module_id;
  IF qs IS DISTINCT FROM 'published' THEN
    RAISE EXCEPTION 'Question % must be published to be placed in a module', NEW.question_id USING ERRCODE = 'check_violation';
  END IF;
  IF qsec IS DISTINCT FROM msec THEN
    RAISE EXCEPTION 'Question % (section %) does not belong in a % module', NEW.question_id, qsec, msec USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_validate_module_question BEFORE INSERT OR UPDATE ON module_questions
  FOR EACH ROW EXECUTE FUNCTION trg_validate_module_question();

CREATE FUNCTION trg_validate_blueprint_domain() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE dsec section_type; msec section_type;
BEGIN
  SELECT section INTO dsec FROM domains WHERE id = NEW.domain_id;
  SELECT ts.section INTO msec FROM test_modules tm JOIN test_sections ts ON ts.id = tm.section_id
    WHERE tm.id = NEW.module_id;
  IF dsec IS DISTINCT FROM msec THEN
    RAISE EXCEPTION 'Blueprint domain section % does not match module section %', dsec, msec USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_validate_blueprint_domain BEFORE INSERT OR UPDATE ON module_blueprints
  FOR EACH ROW EXECUTE FUNCTION trg_validate_blueprint_domain();

\echo === STEP 51: Trigger: a test cannot be published unless it matches its blueprint ===
CREATE FUNCTION ctrg_validate_test_publishable() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE m record; n int; sec record; bp_rows int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM test_sections WHERE test_id = NEW.id) THEN
    RAISE EXCEPTION 'Test % has no sections', NEW.id USING ERRCODE = 'check_violation';
  END IF;
  FOR m IN
    SELECT tm.id, tm.stage, tm.level, tm.question_target, tm.routing_threshold
      FROM test_modules tm JOIN test_sections ts ON ts.id = tm.section_id WHERE ts.test_id = NEW.id
  LOOP
    SELECT count(*) INTO n FROM module_questions WHERE module_id = m.id;
    IF n <> m.question_target THEN
      RAISE EXCEPTION 'Module % (stage % %) has % questions, expected %', m.id, m.stage, m.level, n, m.question_target
        USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.is_adaptive AND m.stage = 1 AND m.routing_threshold IS NULL THEN
      RAISE EXCEPTION 'Stage-1 module % needs a routing_threshold', m.id USING ERRCODE = 'check_violation';
    END IF;
    IF NOT NEW.is_adaptive AND m.stage = 2 THEN
      RAISE EXCEPTION 'Non-adaptive test % cannot have stage-2 modules', NEW.id USING ERRCODE = 'check_violation';
    END IF;
    SELECT count(*) INTO bp_rows FROM module_blueprints WHERE module_id = m.id;
    IF bp_rows > 0 THEN
      IF (SELECT sum(question_count) FROM module_blueprints WHERE module_id = m.id) <> m.question_target THEN
        RAISE EXCEPTION 'Blueprint of module % does not add up to % questions', m.id, m.question_target USING ERRCODE = 'check_violation';
      END IF;
      IF EXISTS (
        SELECT 1 FROM module_blueprints b
         WHERE b.module_id = m.id AND (
           (SELECT count(*) FROM module_questions mq JOIN questions q ON q.id = mq.question_id
             WHERE mq.module_id = b.module_id AND q.domain_id = b.domain_id) <> b.question_count
        OR (SELECT count(*) FROM module_questions mq JOIN questions q ON q.id = mq.question_id
             WHERE mq.module_id = b.module_id AND q.domain_id = b.domain_id AND q.difficulty = 'easy') <> b.easy_count
        OR (SELECT count(*) FROM module_questions mq JOIN questions q ON q.id = mq.question_id
             WHERE mq.module_id = b.module_id AND q.domain_id = b.domain_id AND q.difficulty = 'medium') <> b.medium_count
        OR (SELECT count(*) FROM module_questions mq JOIN questions q ON q.id = mq.question_id
             WHERE mq.module_id = b.module_id AND q.domain_id = b.domain_id AND q.difficulty = 'hard') <> b.hard_count)
      ) THEN
        RAISE EXCEPTION 'Questions of module % do not match its blueprint (domain / difficulty counts)', m.id USING ERRCODE = 'check_violation';
      END IF;
    END IF;
  END LOOP;
  IF NEW.is_adaptive THEN
    FOR sec IN SELECT id FROM test_sections WHERE test_id = NEW.id LOOP
      IF NOT EXISTS (SELECT 1 FROM test_modules WHERE section_id = sec.id AND stage = 1)
         OR NOT EXISTS (SELECT 1 FROM test_modules WHERE section_id = sec.id AND stage = 2 AND level = 'easy')
         OR NOT EXISTS (SELECT 1 FROM test_modules WHERE section_id = sec.id AND stage = 2 AND level = 'hard') THEN
        RAISE EXCEPTION 'Adaptive section % needs a router module plus easy and hard stage-2 modules', sec.id USING ERRCODE = 'check_violation';
      END IF;
    END LOOP;
  END IF;
  RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER ctrg_test_publishable_ins AFTER INSERT ON tests
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.status = 'published')
  EXECUTE FUNCTION ctrg_validate_test_publishable();
CREATE CONSTRAINT TRIGGER ctrg_test_publishable_upd AFTER UPDATE OF status ON tests
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.status = 'published' AND OLD.status IS DISTINCT FROM 'published')
  EXECUTE FUNCTION ctrg_validate_test_publishable();

\echo === STEP 52: Trigger: hard module boundary (no writes after submit or deadline) ===
CREATE FUNCTION trg_block_late_writes() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE ma record; qr record;
BEGIN
  SELECT status, deadline_at, module_id INTO ma FROM module_attempts WHERE id = NEW.module_attempt_id;

  IF TG_TABLE_NAME = 'answers' THEN
    -- only the grading roles may write is_correct, and only once the module is submitted
    IF TG_OP = 'UPDATE' AND session_user IN ('app_grader', 'app_owner', 'postgres')
       AND OLD.is_correct IS NULL AND NEW.is_correct IS NOT NULL
       AND (NEW.module_attempt_id, NEW.question_id, NEW.selected_choice_id, NEW.response_text,
            NEW.eliminated_choice_ids, NEW.is_flagged, NEW.time_spent_ms, NEW.visit_count, NEW.revision)
           IS NOT DISTINCT FROM
           (OLD.module_attempt_id, OLD.question_id, OLD.selected_choice_id, OLD.response_text,
            OLD.eliminated_choice_ids, OLD.is_flagged, OLD.time_spent_ms, OLD.visit_count, OLD.revision) THEN
      RETURN NEW;
    END IF;
    IF NEW.is_correct IS NOT NULL AND session_user NOT IN ('app_grader', 'app_owner', 'postgres') THEN
      RAISE EXCEPTION 'is_correct is set by the server at grading time only' USING ERRCODE = 'insufficient_privilege';
    END IF;
    -- identity of an answer row never changes
    IF TG_OP = 'UPDATE' AND (NEW.question_id, NEW.module_attempt_id, NEW.user_id, NEW.section, NEW.domain_id, NEW.skill_id, NEW.difficulty)
       IS DISTINCT FROM (OLD.question_id, OLD.module_attempt_id, OLD.user_id, OLD.section, OLD.domain_id, OLD.skill_id, OLD.difficulty) THEN
      RAISE EXCEPTION 'question, owner and category columns of an answer cannot be changed' USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  IF ma.status IS DISTINCT FROM 'in_progress' THEN
    RAISE EXCEPTION 'Module attempt % is not in progress; writes are closed', NEW.module_attempt_id
      USING ERRCODE = 'check_violation';
  END IF;
  IF now() > ma.deadline_at + interval '2 seconds' THEN
    RAISE EXCEPTION 'Module attempt % passed its deadline (%)', NEW.module_attempt_id, ma.deadline_at
      USING ERRCODE = 'check_violation';
  END IF;

  -- on first write: the question must belong to this module, and the category snapshot is copied
  -- from the question by the database (the client cannot choose it)
  IF TG_TABLE_NAME = 'answers' AND TG_OP = 'INSERT' THEN
    SELECT q.section, q.domain_id, q.skill_id, q.difficulty INTO qr
      FROM questions q JOIN module_questions mq ON mq.question_id = q.id
     WHERE q.id = NEW.question_id AND mq.module_id = ma.module_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Question % is not part of this module', NEW.question_id USING ERRCODE = 'check_violation';
    END IF;
    NEW.section := qr.section;
    NEW.domain_id := qr.domain_id;
    NEW.skill_id := qr.skill_id;
    NEW.difficulty := qr.difficulty;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_block_late_writes BEFORE INSERT OR UPDATE ON answers
  FOR EACH ROW EXECUTE FUNCTION trg_block_late_writes();
CREATE TRIGGER trg_block_late_writes BEFORE INSERT OR UPDATE ON annotations
  FOR EACH ROW EXECUTE FUNCTION trg_block_late_writes();

\echo === STEP 53: Trigger: submitted modules are immutable and modules run in order ===
CREATE FUNCTION trg_immutable_submitted() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'submitted' THEN
    IF (NEW.attempt_id, NEW.user_id, NEW.module_id, NEW.sequence, NEW.status, NEW.started_at,
        NEW.deadline_at, NEW.submitted_at, NEW.submit_reason)
       IS DISTINCT FROM
       (OLD.attempt_id, OLD.user_id, OLD.module_id, OLD.sequence, OLD.status, OLD.started_at,
        OLD.deadline_at, OLD.submitted_at, OLD.submit_reason) THEN
      RAISE EXCEPTION 'Submitted module attempt % is immutable', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    IF (OLD.question_count IS NOT NULL AND NEW.question_count IS DISTINCT FROM OLD.question_count)
       OR (OLD.correct_count IS NOT NULL AND NEW.correct_count IS DISTINCT FROM OLD.correct_count)
       OR (OLD.weighted_score IS NOT NULL AND NEW.weighted_score IS DISTINCT FROM OLD.weighted_score) THEN
      RAISE EXCEPTION 'Grading fields of module attempt % are write-once', OLD.id USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_immutable_submitted BEFORE UPDATE ON module_attempts
  FOR EACH ROW EXECUTE FUNCTION trg_immutable_submitted();

CREATE FUNCTION trg_enforce_module_order() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE md record; prev record;
BEGIN
  IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
    RETURN NEW;
  END IF;
  IF NOT ((OLD.status = 'not_started' AND NEW.status = 'in_progress')
       OR (OLD.status = 'in_progress' AND NEW.status = 'submitted')) THEN
    RAISE EXCEPTION 'Invalid module status transition % -> %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
  END IF;

  IF NEW.status = 'in_progress' THEN
    -- 1. earlier modules must be submitted
    IF EXISTS (SELECT 1 FROM module_attempts p
                WHERE p.attempt_id = NEW.attempt_id AND p.sequence < NEW.sequence AND p.status <> 'submitted') THEN
      RAISE EXCEPTION 'Earlier modules of this attempt must be submitted first' USING ERRCODE = 'check_violation';
    END IF;

    SELECT tm.stage, ts.position, ts.test_id INTO md
      FROM test_modules tm JOIN test_sections ts ON ts.id = tm.section_id WHERE tm.id = NEW.module_id;

    -- 2. a stage-2 module must be the one chosen by the routing decision
    IF md.stage = 2 AND NOT EXISTS (
         SELECT 1 FROM routing_decisions rd JOIN module_attempts f ON f.id = rd.from_module_attempt_id
          WHERE f.attempt_id = NEW.attempt_id AND rd.to_module_id = NEW.module_id) THEN
      RAISE EXCEPTION 'This stage-2 module was not chosen by routing' USING ERRCODE = 'check_violation';
    END IF;

    -- 3. entering a later section requires the break to be finished or skipped
    IF md.stage = 1 AND md.position > 1 THEN
      SELECT id, break_seconds INTO prev FROM test_sections
       WHERE test_id = md.test_id AND position = md.position - 1;
      IF prev.break_seconds IS NOT NULL AND NOT EXISTS (
           SELECT 1 FROM break_sessions b
            WHERE b.attempt_id = NEW.attempt_id AND b.after_section_id = prev.id
              AND (b.skipped_at IS NOT NULL OR b.ends_at <= now())) THEN
        RAISE EXCEPTION 'The break after the previous section is not finished or skipped' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_enforce_module_order BEFORE UPDATE OF status ON module_attempts
  FOR EACH ROW EXECUTE FUNCTION trg_enforce_module_order();

\echo === STEP 54: Trigger: logs are append-only ===
-- Logs can only be changed by the database's own foreign-key actions
-- (e.g. ON DELETE CASCADE / SET NULL when an account is erased). pg_trigger_depth() > 1
-- means "fired from inside another trigger", which is exactly that case.
CREATE FUNCTION trg_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF pg_trigger_depth() > 1 THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  RAISE EXCEPTION '% is append-only (% not allowed)', TG_TABLE_NAME, TG_OP USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE FUNCTION trg_no_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only (TRUNCATE not allowed)', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON answer_events
  FOR EACH ROW EXECUTE FUNCTION trg_append_only();
CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON auth_events
  FOR EACH ROW EXECUTE FUNCTION trg_append_only();
CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON audit_logs
  FOR EACH ROW EXECUTE FUNCTION trg_append_only();
CREATE TRIGGER trg_no_truncate BEFORE TRUNCATE ON answer_events
  FOR EACH STATEMENT EXECUTE FUNCTION trg_no_truncate();
CREATE TRIGGER trg_no_truncate BEFORE TRUNCATE ON auth_events
  FOR EACH STATEMENT EXECUTE FUNCTION trg_no_truncate();
CREATE TRIGGER trg_no_truncate BEFORE TRUNCATE ON audit_logs
  FOR EACH STATEMENT EXECUTE FUNCTION trg_no_truncate();

\echo === STEP 55: Trigger: never remove the last admin ===
CREATE FUNCTION trg_last_admin_guard() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF OLD.role = 'admin' AND OLD.is_active AND OLD.deleted_at IS NULL THEN
    IF TG_OP = 'DELETE' OR NEW.role <> 'admin' OR NOT NEW.is_active OR NEW.deleted_at IS NOT NULL THEN
      IF NOT EXISTS (SELECT 1 FROM users u WHERE u.role = 'admin' AND u.is_active AND u.deleted_at IS NULL AND u.id <> OLD.id) THEN
        RAISE EXCEPTION 'Cannot remove, demote or deactivate the last active admin' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_last_admin_guard BEFORE UPDATE OR DELETE ON users
  FOR EACH ROW EXECUTE FUNCTION trg_last_admin_guard();

\echo === STEP 56: Create security helper functions and views ===
-- SECURITY DEFINER helpers (owner has BYPASSRLS) so policies never recurse into each other.
CREATE FUNCTION is_class_teacher_of(student uuid, require_sharing boolean) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT EXISTS (
    SELECT 1 FROM class_members cm JOIN classes c ON c.id = cm.class_id
     WHERE cm.user_id = student AND c.teacher_id = app_uid() AND cm.removed_at IS NULL
       AND (NOT require_sharing OR cm.results_visible_to_teacher))
$$;

CREATE FUNCTION is_class_owner(cid uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM classes WHERE id = cid AND teacher_id = app_uid())
$$;

CREATE FUNCTION is_class_member(cid uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM class_members WHERE class_id = cid AND user_id = app_uid() AND removed_at IS NULL)
$$;

-- Logging functions: the API role cannot write the log tables directly.
CREATE FUNCTION log_answer_event(p_attempt uuid, p_question uuid, p_type answer_event_type,
                                 p_payload jsonb, p_client_ts timestamptz) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM module_attempts WHERE id = p_attempt AND user_id = app_uid()) THEN
    RAISE EXCEPTION 'Not your module attempt' USING ERRCODE = 'insufficient_privilege';
  END IF;
  INSERT INTO answer_events (module_attempt_id, question_id, event_type, payload, client_ts)
  VALUES (p_attempt, p_question, p_type, p_payload, p_client_ts);
END $$;

CREATE FUNCTION log_audit(p_action text, p_entity_type text, p_entity_id uuid, p_before jsonb,
                          p_after jsonb, p_ip inet, p_request uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF app_role() IS DISTINCT FROM 'admin'
     AND session_user NOT IN ('app_content_admin', 'app_worker', 'app_grader', 'app_auth') THEN
    RAISE EXCEPTION 'Not allowed to write audit logs' USING ERRCODE = 'insufficient_privilege';
  END IF;
  INSERT INTO audit_logs (actor_user_id, action, entity_type, entity_id, before_data, after_data, ip, request_id)
  VALUES (app_uid(), p_action, p_entity_type, p_entity_id, p_before, p_after, p_ip, p_request);
END $$;

-- Views
CREATE VIEW v_serving_questions WITH (security_invoker = true) AS
  SELECT q.id, q.section, q.domain_id, q.skill_id, q.passage_id, q.question_type, q.stem,
         q.stem_asset_key, q.calculator_allowed
    FROM questions q WHERE q.status = 'published';

CREATE VIEW v_serving_choices WITH (security_invoker = true) AS
  SELECT c.id, c.question_id, c.label, c.content, c.asset_key, c.position
    FROM question_choices c JOIN questions q ON q.id = c.question_id WHERE q.status = 'published';

CREATE VIEW v_my_answers WITH (security_invoker = true) AS
  SELECT a.id, a.module_attempt_id, a.question_id, a.selected_choice_id, a.response_text,
         a.eliminated_choice_ids, a.is_flagged, a.time_spent_ms, a.visit_count, a.revision,
         CASE WHEN ma.status = 'submitted' THEN a.is_correct END AS is_correct, a.updated_at
    FROM answers a JOIN module_attempts ma ON ma.id = a.module_attempt_id;

CREATE VIEW v_analytics_answers AS
  SELECT md5(a.user_id::text || coalesce(current_setting('app.pseudonym_salt', true), '')) AS student_pseudo,
         a.section, a.domain_id, a.skill_id, a.difficulty, a.is_correct, a.time_spent_ms, a.created_at
    FROM answers a WHERE a.is_correct IS NOT NULL;

CREATE VIEW v_analytics_skill_stats AS
  SELECT md5(s.user_id::text || coalesce(current_setting('app.pseudonym_salt', true), '')) AS student_pseudo,
         s.skill_id, s.total_answered, s.total_correct, s.accuracy_pct, s.mastery, s.avg_time_ms
    FROM user_skill_stats s;

\echo === STEP 57: Turn on Row-Level Security and create all policies ===
-- Turn RLS on for every protected table. Tables with no policy below deny everything to app_rw.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE test_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_attempts FORCE ROW LEVEL SECURITY;
ALTER TABLE module_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE module_attempts FORCE ROW LEVEL SECURITY;
ALTER TABLE answers ENABLE ROW LEVEL SECURITY;
ALTER TABLE answers FORCE ROW LEVEL SECURITY;
ALTER TABLE annotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotations FORCE ROW LEVEL SECURITY;
ALTER TABLE break_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE break_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE routing_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE routing_decisions FORCE ROW LEVEL SECURITY;
ALTER TABLE score_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE score_reports FORCE ROW LEVEL SECURITY;
ALTER TABLE domain_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE domain_results FORCE ROW LEVEL SECURITY;
ALTER TABLE skill_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_results FORCE ROW LEVEL SECURITY;
ALTER TABLE user_skill_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_skill_stats FORCE ROW LEVEL SECURITY;
ALTER TABLE user_domain_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_domain_stats FORCE ROW LEVEL SECURITY;
ALTER TABLE user_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_stats FORCE ROW LEVEL SECURITY;
ALTER TABLE user_goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_goals FORCE ROW LEVEL SECURITY;
ALTER TABLE user_consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_consents FORCE ROW LEVEL SECURITY;
ALTER TABLE data_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_requests FORCE ROW LEVEL SECURITY;
ALTER TABLE classes ENABLE ROW LEVEL SECURITY;
ALTER TABLE classes FORCE ROW LEVEL SECURITY;
ALTER TABLE class_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE class_members FORCE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens FORCE ROW LEVEL SECURITY;
ALTER TABLE password_reset_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_reset_tokens FORCE ROW LEVEL SECURITY;
ALTER TABLE email_verification_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_verification_tokens FORCE ROW LEVEL SECURITY;
ALTER TABLE answer_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE answer_events FORCE ROW LEVEL SECURITY;
ALTER TABLE auth_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_events FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

-- users
CREATE POLICY pol_users_self_select ON users FOR SELECT TO app_rw USING (id = app_uid());
CREATE POLICY pol_users_self_update ON users FOR UPDATE TO app_rw USING (id = app_uid()) WITH CHECK (id = app_uid());
CREATE POLICY pol_users_teacher_read ON users FOR SELECT TO app_rw USING (is_class_teacher_of(id, false));

-- attempts, modules, answers
CREATE POLICY pol_attempts_owner ON test_attempts FOR ALL TO app_rw USING (user_id = app_uid()) WITH CHECK (user_id = app_uid());
CREATE POLICY pol_attempts_teacher_read ON test_attempts FOR SELECT TO app_rw USING (is_class_teacher_of(user_id, true));
CREATE POLICY pol_module_attempts_owner ON module_attempts FOR ALL TO app_rw USING (user_id = app_uid()) WITH CHECK (user_id = app_uid());
CREATE POLICY pol_module_attempts_teacher_read ON module_attempts FOR SELECT TO app_rw USING (is_class_teacher_of(user_id, true));
CREATE POLICY pol_answers_owner_select ON answers FOR SELECT TO app_rw USING (user_id = app_uid());
CREATE POLICY pol_answers_owner_insert ON answers FOR INSERT TO app_rw
  WITH CHECK (user_id = app_uid() AND EXISTS (SELECT 1 FROM module_attempts ma WHERE ma.id = module_attempt_id AND ma.status = 'in_progress'));
CREATE POLICY pol_answers_owner_update ON answers FOR UPDATE TO app_rw
  USING (user_id = app_uid())
  WITH CHECK (user_id = app_uid() AND EXISTS (SELECT 1 FROM module_attempts ma WHERE ma.id = module_attempt_id AND ma.status = 'in_progress'));
CREATE POLICY pol_answers_teacher_read ON answers FOR SELECT TO app_rw USING (is_class_teacher_of(user_id, true));
CREATE POLICY pol_annotations_owner ON annotations FOR ALL TO app_rw USING (user_id = app_uid()) WITH CHECK (user_id = app_uid());
CREATE POLICY pol_break_owner ON break_sessions FOR ALL TO app_rw USING (user_id = app_uid()) WITH CHECK (user_id = app_uid());
CREATE POLICY pol_routing_owner_read ON routing_decisions FOR SELECT TO app_rw
  USING (EXISTS (SELECT 1 FROM module_attempts ma WHERE ma.id = from_module_attempt_id));

-- results and stats
CREATE POLICY pol_reports_owner ON score_reports FOR SELECT TO app_rw USING (user_id = app_uid());
CREATE POLICY pol_reports_teacher_read ON score_reports FOR SELECT TO app_rw USING (is_class_teacher_of(user_id, true));
CREATE POLICY pol_domain_results_via_report ON domain_results FOR SELECT TO app_rw
  USING (EXISTS (SELECT 1 FROM score_reports sr WHERE sr.id = report_id));
CREATE POLICY pol_skill_results_via_report ON skill_results FOR SELECT TO app_rw
  USING (EXISTS (SELECT 1 FROM score_reports sr WHERE sr.id = report_id));
CREATE POLICY pol_uss_owner ON user_skill_stats FOR SELECT TO app_rw USING (user_id = app_uid());
CREATE POLICY pol_uss_teacher_read ON user_skill_stats FOR SELECT TO app_rw USING (is_class_teacher_of(user_id, true));
CREATE POLICY pol_uds_owner ON user_domain_stats FOR SELECT TO app_rw USING (user_id = app_uid());
CREATE POLICY pol_uds_teacher_read ON user_domain_stats FOR SELECT TO app_rw USING (is_class_teacher_of(user_id, true));
CREATE POLICY pol_user_stats_owner ON user_stats FOR SELECT TO app_rw USING (user_id = app_uid());
CREATE POLICY pol_user_stats_teacher_read ON user_stats FOR SELECT TO app_rw USING (is_class_teacher_of(user_id, true));
CREATE POLICY pol_goals_owner ON user_goals FOR ALL TO app_rw USING (user_id = app_uid()) WITH CHECK (user_id = app_uid());

-- consent, privacy requests
CREATE POLICY pol_consents_owner_select ON user_consents FOR SELECT TO app_rw USING (user_id = app_uid());
CREATE POLICY pol_consents_owner_insert ON user_consents FOR INSERT TO app_rw WITH CHECK (user_id = app_uid());
CREATE POLICY pol_data_requests_owner_select ON data_requests FOR SELECT TO app_rw USING (user_id = app_uid());
CREATE POLICY pol_data_requests_owner_insert ON data_requests FOR INSERT TO app_rw WITH CHECK (user_id = app_uid());

-- classes
CREATE POLICY pol_classes_teacher ON classes FOR ALL TO app_rw USING (teacher_id = app_uid()) WITH CHECK (teacher_id = app_uid());
CREATE POLICY pol_classes_member_read ON classes FOR SELECT TO app_rw USING (is_class_member(id));
CREATE POLICY pol_class_members_self ON class_members FOR SELECT TO app_rw USING (user_id = app_uid());
CREATE POLICY pol_class_members_teacher ON class_members FOR ALL TO app_rw USING (is_class_owner(class_id)) WITH CHECK (is_class_owner(class_id));

-- admin can see and manage everything above (users included)
CREATE POLICY pol_users_admin ON users FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_test_attempts_admin ON test_attempts FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_module_attempts_admin ON module_attempts FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_answers_admin ON answers FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_annotations_admin ON annotations FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_break_sessions_admin ON break_sessions FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_routing_decisions_admin ON routing_decisions FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_score_reports_admin ON score_reports FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_domain_results_admin ON domain_results FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_skill_results_admin ON skill_results FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_user_skill_stats_admin ON user_skill_stats FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_user_domain_stats_admin ON user_domain_stats FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_user_stats_admin ON user_stats FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_user_goals_admin ON user_goals FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_user_consents_admin ON user_consents FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_data_requests_admin ON data_requests FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_classes_admin ON classes FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY pol_class_members_admin ON class_members FOR ALL TO app_rw USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');

-- refresh_tokens, password_reset_tokens, email_verification_tokens, answer_events, auth_events, audit_logs:
-- RLS is on and there is deliberately NO policy for app_rw, so it is denied everything.
-- (app_auth, app_worker, app_grader and app_content_admin have BYPASSRLS.)

\echo === STEP 58: Grant least-privilege table access to each role ===
-- app_rw : the API runtime role
GRANT SELECT ON domains, skills, passages, questions, question_choices, tests, test_sections, test_modules,
      module_blueprints, module_questions, score_conversions,
      v_serving_questions, v_serving_choices, v_my_answers TO app_rw;
GRANT SELECT, INSERT, UPDATE ON test_attempts, module_attempts, break_sessions, answers, classes TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON annotations, user_goals, class_members, idempotency_keys TO app_rw;
GRANT SELECT, INSERT ON user_consents, data_requests TO app_rw;
GRANT SELECT ON routing_decisions, score_reports, domain_results, skill_results,
      user_skill_stats, user_domain_stats, user_stats TO app_rw;
-- users: never expose password_hash; only profile columns are updatable
GRANT SELECT (id, email, full_name, role, is_active, email_verified_at, last_login_at, target_score, test_date,
              timezone, grade_level, birth_year, signup_source, onboarding_completed_at, created_at, updated_at) ON users TO app_rw;
GRANT UPDATE (full_name, target_score, test_date, timezone, grade_level, onboarding_completed_at) ON users TO app_rw;
GRANT EXECUTE ON FUNCTION log_answer_event(uuid, uuid, answer_event_type, jsonb, timestamptz) TO app_rw;
GRANT EXECUTE ON FUNCTION log_audit(text, text, uuid, jsonb, jsonb, inet, uuid) TO app_rw, app_content_admin, app_worker, app_grader, app_auth;

-- app_grader : grading code path (separate connection pool)
GRANT SELECT ON ALL TABLES IN SCHEMA grading TO app_grader;
GRANT SELECT ON answers, module_attempts, test_attempts, test_modules, test_sections, module_questions,
      questions, question_choices TO app_grader;
GRANT UPDATE (is_correct) ON answers TO app_grader;
GRANT UPDATE (status, submitted_at, submit_reason, question_count, correct_count, weighted_score) ON module_attempts TO app_grader;
GRANT INSERT ON routing_decisions, module_attempts, break_sessions TO app_grader;

-- app_auth : authentication service
GRANT SELECT, INSERT, UPDATE, DELETE ON refresh_tokens, password_reset_tokens, email_verification_tokens TO app_auth;
GRANT SELECT, INSERT ON auth_events TO app_auth;
GRANT SELECT, INSERT, UPDATE ON users, user_consents TO app_auth;

-- app_content_admin : content tools
GRANT SELECT, INSERT, UPDATE, DELETE ON passages, questions, question_choices, tests, test_sections, test_modules,
      module_blueprints, module_questions, score_conversions, domains, skills TO app_content_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA grading TO app_content_admin;

-- app_worker : background jobs
GRANT SELECT ON answers, test_attempts, module_attempts, routing_decisions, questions, domains, skills,
      test_modules, test_sections, module_questions TO app_worker;
GRANT UPDATE (status, completed_at, last_activity_at) ON test_attempts TO app_worker;
GRANT SELECT, INSERT, UPDATE ON score_reports, domain_results, skill_results, user_skill_stats,
      user_domain_stats, user_stats, question_stats TO app_worker;
GRANT SELECT, UPDATE ON data_requests TO app_worker;
GRANT DELETE ON idempotency_keys TO app_worker;
GRANT SELECT ON answer_events TO app_worker;

-- analytics_ro : de-identified views only
GRANT SELECT ON v_analytics_answers, v_analytics_skill_stats TO analytics_ro;

-- Nothing is granted to any application role on: answer_events, auth_events, audit_logs (writes go through
-- log_* functions / app_auth) and nothing on the grading schema except app_grader and app_content_admin.

\echo === STEP 59: Tune autovacuum for the busy tables ===
-- Aggressive autovacuum for high-churn tables
ALTER TABLE answers          SET (autovacuum_vacuum_scale_factor = 0.02, autovacuum_analyze_scale_factor = 0.02);
ALTER TABLE module_attempts  SET (autovacuum_vacuum_scale_factor = 0.02, autovacuum_analyze_scale_factor = 0.02);
ALTER TABLE refresh_tokens   SET (autovacuum_vacuum_scale_factor = 0.02);
ALTER TABLE idempotency_keys SET (autovacuum_vacuum_scale_factor = 0.02);

\echo === STEP 60: Seed the 8 domains and 29 skills ===
INSERT INTO domains (section, code, name, position) VALUES
  ('RW', 'RW_INFO', 'Information and Ideas', 1),
  ('RW', 'RW_CRAFT', 'Craft and Structure', 2),
  ('RW', 'RW_EXPR', 'Expression of Ideas', 3),
  ('RW', 'RW_CONV', 'Standard English Conventions', 4),
  ('MATH', 'M_ALG', 'Algebra', 1),
  ('MATH', 'M_ADV', 'Advanced Math', 2),
  ('MATH', 'M_PSDA', 'Problem-Solving and Data Analysis', 3),
  ('MATH', 'M_GEO', 'Geometry and Trigonometry', 4);

INSERT INTO skills (domain_id, section, code, name, position)
SELECT d.id, d.section, v.code, v.name, v.position
  FROM (VALUES
  ('RW_CENTRAL', 'RW_INFO', 'Central Ideas and Details', 1),
  ('RW_INFERENCE', 'RW_INFO', 'Inference', 2),
  ('RW_EVIDENCE', 'RW_INFO', 'Command of Evidence', 3),
  ('RW_WORDS', 'RW_CRAFT', 'Words in Context', 1),
  ('RW_STRUCTURE', 'RW_CRAFT', 'Text Structure and Purpose', 2),
  ('RW_CROSSTEXT', 'RW_CRAFT', 'Cross-Text Connections', 3),
  ('RW_SYNTHESIS', 'RW_EXPR', 'Rhetorical Synthesis', 1),
  ('RW_TRANSITIONS', 'RW_EXPR', 'Transitions', 2),
  ('RW_BOUNDARIES', 'RW_CONV', 'Boundaries', 1),
  ('RW_FSS', 'RW_CONV', 'Form, Structure, and Sense', 2),
  ('M_LIN_EQ_1V', 'M_ALG', 'Linear Equations in One Variable', 1),
  ('M_LIN_FUNC', 'M_ALG', 'Linear Functions', 2),
  ('M_LIN_EQ_2V', 'M_ALG', 'Linear Equations in Two Variables', 3),
  ('M_LIN_SYSTEMS', 'M_ALG', 'Systems of Two Linear Equations in Two Variables', 4),
  ('M_LIN_INEQ', 'M_ALG', 'Linear Inequalities in One or Two Variables', 5),
  ('M_NONLIN_FUNC', 'M_ADV', 'Nonlinear Functions', 1),
  ('M_NONLIN_EQ', 'M_ADV', 'Nonlinear Equations in One Variable and Systems of Equations in Two Variables', 2),
  ('M_EQUIV_EXPR', 'M_ADV', 'Equivalent Expressions', 3),
  ('M_RATIOS', 'M_PSDA', 'Ratios, Rates, Proportional Relationships, and Units', 1),
  ('M_PERCENT', 'M_PSDA', 'Percentages', 2),
  ('M_ONE_VAR_DATA', 'M_PSDA', 'One-Variable Data: Distributions and Measures of Center and Spread', 3),
  ('M_TWO_VAR_DATA', 'M_PSDA', 'Two-Variable Data: Models and Scatterplots', 4),
  ('M_PROBABILITY', 'M_PSDA', 'Probability and Conditional Probability', 5),
  ('M_INFERENCE', 'M_PSDA', 'Inference from Sample Statistics and Margin of Error', 6),
  ('M_STAT_CLAIMS', 'M_PSDA', 'Evaluating Statistical Claims: Observational Studies and Experiments', 7),
  ('M_AREA_VOLUME', 'M_GEO', 'Area and Volume', 1),
  ('M_LINES_ANGLES', 'M_GEO', 'Lines, Angles, and Triangles', 2),
  ('M_RIGHT_TRIG', 'M_GEO', 'Right Triangles and Trigonometry', 3),
  ('M_CIRCLES', 'M_GEO', 'Circles', 4)
  ) AS v(code, domain_code, name, position)
  JOIN domains d ON d.code = v.domain_code;

\echo === STEP 61: Add column comments (documentation inside the database) ===
COMMENT ON COLUMN users.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN users.email IS 'Unique via index on lower(email). Always store and compare lower-cased.';
COMMENT ON COLUMN users.password_hash IS 'argon2id (preferred) or bcrypt cost >= 12. Never returned by any API.';
COMMENT ON COLUMN users.role IS 'student / teacher / admin. Role changes are written to audit_logs.';
COMMENT ON COLUMN users.is_active IS 'false blocks login and token refresh immediately';
COMMENT ON COLUMN users.failed_login_count IS 'Reset on successful login; lockout input';
COMMENT ON COLUMN users.locked_until IS 'Temporary lockout after repeated failures';
COMMENT ON COLUMN users.password_changed_at IS 'Tokens issued before this time are rejected';
COMMENT ON COLUMN users.target_score IS '400-1600';
COMMENT ON COLUMN users.test_date IS 'Planned real SAT date (date, not timestamp)';
COMMENT ON COLUMN users.timezone IS 'IANA name, e.g. Africa/Addis_Ababa';
COMMENT ON COLUMN users.grade_level IS '9-12';
COMMENT ON COLUMN users.birth_year IS 'Year only (data minimisation). Drives age-gate / parental-consent flow.';
COMMENT ON COLUMN users.deleted_at IS 'Set when deletion is requested; job anonymises PII and keeps de-identified aggregates';
COMMENT ON COLUMN users.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN users.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN refresh_tokens.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN refresh_tokens.user_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN refresh_tokens.family_id IS 'All tokens descending from one login share a family. Reuse of a revoked token revokes the whole family.';
COMMENT ON COLUMN refresh_tokens.token_hash IS 'SHA-256 hex of the opaque token. The raw token is never stored.';
COMMENT ON COLUMN refresh_tokens.replaced_by_id IS 'ON DELETE SET NULL. Set when rotated.';
COMMENT ON COLUMN refresh_tokens.revoke_reason IS 'rotated / logout / reuse_detected / password_change / admin';
COMMENT ON COLUMN refresh_tokens.ip IS 'Personal data under GDPR. Covered by retention rule.';
COMMENT ON COLUMN refresh_tokens.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN password_reset_tokens.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN password_reset_tokens.user_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN password_reset_tokens.token_hash IS 'SHA-256 hex';
COMMENT ON COLUMN password_reset_tokens.expires_at IS 'Recommended lifetime: 30 minutes';
COMMENT ON COLUMN password_reset_tokens.used_at IS 'Single use: non-null means consumed';
COMMENT ON COLUMN password_reset_tokens.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN email_verification_tokens.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN email_verification_tokens.user_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN email_verification_tokens.new_email IS 'Non-null only for an email-change flow';
COMMENT ON COLUMN email_verification_tokens.token_hash IS 'SHA-256 hex';
COMMENT ON COLUMN email_verification_tokens.expires_at IS 'Recommended lifetime: 24 hours';
COMMENT ON COLUMN email_verification_tokens.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN user_consents.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN user_consents.user_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN user_consents.document_version IS 'Version of the document the user agreed to';
COMMENT ON COLUMN user_consents.guardian_email IS 'For users under the digital-consent age';
COMMENT ON COLUMN auth_events.id IS 'Composite PK with created_at (partition key)';
COMMENT ON COLUMN auth_events.created_at IS 'Partition key';
COMMENT ON COLUMN auth_events.user_id IS 'ON DELETE SET NULL (event survives for security forensics)';
COMMENT ON COLUMN auth_events.identifier_hash IS 'SHA-256 of the attempted email (no raw email for unknown accounts)';
COMMENT ON COLUMN auth_events.metadata IS 'Auxiliary details only, never queried relationally';
COMMENT ON COLUMN classes.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN classes.teacher_id IS 'ON DELETE RESTRICT (reassign before deleting a teacher)';
COMMENT ON COLUMN classes.join_code IS 'Random, non-guessable; rotatable';
COMMENT ON COLUMN classes.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN classes.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN class_members.class_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN class_members.user_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN class_members.member_role IS 'student / co_teacher';
COMMENT ON COLUMN class_members.results_visible_to_teacher IS 'Student/guardian privacy switch; RLS honours it';
COMMENT ON COLUMN domains.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN domains.section IS 'RW / MATH';
COMMENT ON COLUMN domains.code IS 'Stable machine code, e.g. M_ALG';
COMMENT ON COLUMN domains.position IS 'Display order within section';
COMMENT ON COLUMN domains.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN skills.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN skills.domain_id IS 'ON DELETE RESTRICT';
COMMENT ON COLUMN skills.section IS 'Copied from domain; composite FK (domain_id, section) keeps it consistent';
COMMENT ON COLUMN skills.code IS 'Stable machine code, e.g. M_LIN_EQ_1V';
COMMENT ON COLUMN skills.position IS 'Display order within domain';
COMMENT ON COLUMN skills.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN passages.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN passages.content IS 'Sanitised HTML/Markdown with KaTeX. Sanitised on write, not only on render.';
COMMENT ON COLUMN passages.asset_key IS 'S3 object key (not a public URL); served via signed URL';
COMMENT ON COLUMN passages.source IS 'Provenance / licence reference';
COMMENT ON COLUMN passages.created_by IS 'ON DELETE SET NULL';
COMMENT ON COLUMN passages.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN passages.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN questions.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN questions.root_question_id IS 'Id of revision 1. Equals id for the first revision. ON DELETE RESTRICT';
COMMENT ON COLUMN questions.revision IS 'Incremented on every content change after publish';
COMMENT ON COLUMN questions.supersedes_id IS 'Previous revision. ON DELETE RESTRICT';
COMMENT ON COLUMN questions.section IS 'Copied from skill';
COMMENT ON COLUMN questions.domain_id IS 'Copied from skill';
COMMENT ON COLUMN questions.skill_id IS 'Single source of truth. Composite FK (skill_id, domain_id, section) prevents contradictory categories.';
COMMENT ON COLUMN questions.passage_id IS 'ON DELETE RESTRICT. Reading & Writing only.';
COMMENT ON COLUMN questions.question_type IS 'multiple_choice / grid_in (no essay: SAT has none)';
COMMENT ON COLUMN questions.stem IS 'Question text, sanitised, KaTeX allowed';
COMMENT ON COLUMN questions.stem_asset_key IS 'Figure / graph / table image (S3 key)';
COMMENT ON COLUMN questions.difficulty IS 'easy / medium / hard: the editorial difficulty of this question';
COMMENT ON COLUMN questions.calculator_allowed IS 'Drives Desmos availability';
COMMENT ON COLUMN questions.irt_a IS 'Discrimination (calibrated later)';
COMMENT ON COLUMN questions.irt_b IS 'IRT difficulty (calibrated later)';
COMMENT ON COLUMN questions.irt_c IS 'Guessing parameter (calibrated later)';
COMMENT ON COLUMN questions.source IS 'Provenance, e.g. original_authored, licensed_pack_2026';
COMMENT ON COLUMN questions.tags IS 'Free-form tags (GIN indexed)';
COMMENT ON COLUMN questions.status IS 'draft / in_review / published / archived';
COMMENT ON COLUMN questions.created_by IS 'ON DELETE SET NULL';
COMMENT ON COLUMN questions.reviewed_by IS 'ON DELETE SET NULL. Four-eyes publish rule.';
COMMENT ON COLUMN questions.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN questions.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN question_choices.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN question_choices.question_id IS 'ON DELETE CASCADE (drafts only; published are protected by trigger)';
COMMENT ON COLUMN question_choices.label IS 'A-D';
COMMENT ON COLUMN question_choices.content IS 'Sanitised, KaTeX allowed';
COMMENT ON COLUMN question_choices.position IS 'Display order';
COMMENT ON COLUMN grading.question_keys.question_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN grading.question_keys.correct_choice_id IS 'Composite FK (question_id, correct_choice_id) guarantees the choice belongs to this question';
COMMENT ON COLUMN grading.spr_accepted_answers.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN grading.spr_accepted_answers.question_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN grading.spr_accepted_answers.raw_value IS 'Accepted textual form';
COMMENT ON COLUMN grading.spr_accepted_answers.numeric_value IS 'Parsed value used for numeric comparison';
COMMENT ON COLUMN grading.question_explanations.question_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN grading.question_explanations.choice_rationales IS '{ ''A'': ''...'', ''B'': ''...'' } why each option is right or wrong';
COMMENT ON COLUMN grading.question_explanations.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN tests.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN tests.test_type IS 'full_mock / section_practice / skill_practice';
COMMENT ON COLUMN tests.is_adaptive IS 'false => only stage-1 modules, no routing';
COMMENT ON COLUMN tests.content_version IS 'Bumped when structure or question set changes';
COMMENT ON COLUMN tests.created_by IS 'ON DELETE SET NULL';
COMMENT ON COLUMN tests.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN tests.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN test_sections.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN test_sections.test_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN test_sections.position IS '1 = Reading & Writing, 2 = Math';
COMMENT ON COLUMN test_sections.break_seconds IS 'Break AFTER this section (600 = 10 min). NULL = no break.';
COMMENT ON COLUMN test_sections.break_skippable IS 'Configurable skip';
COMMENT ON COLUMN test_modules.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN test_modules.section_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN test_modules.stage IS '1 or 2';
COMMENT ON COLUMN test_modules.level IS 'router (stage 1) / easy / hard (stage 2)';
COMMENT ON COLUMN test_modules.time_limit_sec IS '1920 (R&W, 32 min) / 2100 (Math, 35 min) by default';
COMMENT ON COLUMN test_modules.question_target IS 'Required number of questions (27 R&W / 22 Math)';
COMMENT ON COLUMN test_modules.routing_threshold IS 'Stage 1 only. Weighted accuracy >= threshold routes to hard. Configurable per test.';
COMMENT ON COLUMN test_modules.routing_weight_easy IS 'Stage 1 only. Default 1';
COMMENT ON COLUMN test_modules.routing_weight_medium IS 'Stage 1 only. Default 2';
COMMENT ON COLUMN test_modules.routing_weight_hard IS 'Stage 1 only. Default 3';
COMMENT ON COLUMN module_blueprints.module_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN module_blueprints.domain_id IS 'ON DELETE RESTRICT. Domain must belong to the module''s section.';
COMMENT ON COLUMN module_questions.module_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN module_questions.question_id IS 'ON DELETE RESTRICT';
COMMENT ON COLUMN module_questions.position IS '1-based order within module (unique per module)';
COMMENT ON COLUMN score_conversions.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN score_conversions.test_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN score_conversions.stage2_level IS 'easy or hard. Easy path is capped lower.';
COMMENT ON COLUMN score_conversions.raw_score IS 'Total correct across both modules of the section';
COMMENT ON COLUMN score_conversions.scaled_score IS '200-800';
COMMENT ON COLUMN test_attempts.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN test_attempts.user_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN test_attempts.test_id IS 'ON DELETE RESTRICT';
COMMENT ON COLUMN test_attempts.test_content_version IS 'Version served, so history stays reproducible';
COMMENT ON COLUMN test_attempts.time_multiplier IS 'Extended-time accommodation (1.00-3.00)';
COMMENT ON COLUMN test_attempts.last_activity_at IS 'Used by the abandoned-attempt job';
COMMENT ON COLUMN test_attempts.voided_reason IS 'Admin-only';
COMMENT ON COLUMN test_attempts.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN test_attempts.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN module_attempts.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN module_attempts.attempt_id IS 'Composite FK (attempt_id, user_id). ON DELETE CASCADE';
COMMENT ON COLUMN module_attempts.user_id IS 'Denormalised for RLS and analytics; consistency enforced by composite FK';
COMMENT ON COLUMN module_attempts.module_id IS 'ON DELETE RESTRICT';
COMMENT ON COLUMN module_attempts.sequence IS 'Order inside the attempt (1-4 for a full test)';
COMMENT ON COLUMN module_attempts.deadline_at IS 'started_at + time_limit_sec * time_multiplier. THE source of truth for the timer.';
COMMENT ON COLUMN module_attempts.submit_reason IS 'user / timeout / admin / system';
COMMENT ON COLUMN module_attempts.question_count IS 'Set at grading';
COMMENT ON COLUMN module_attempts.correct_count IS 'Set at grading';
COMMENT ON COLUMN module_attempts.weighted_score IS 'Difficulty-weighted accuracy used for routing (0-1)';
COMMENT ON COLUMN module_attempts.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN module_attempts.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN routing_decisions.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN routing_decisions.from_module_attempt_id IS 'ON DELETE CASCADE. One decision per stage-1 attempt.';
COMMENT ON COLUMN routing_decisions.to_module_id IS 'ON DELETE RESTRICT';
COMMENT ON COLUMN routing_decisions.score IS 'Weighted accuracy at decision time';
COMMENT ON COLUMN routing_decisions.threshold IS 'Threshold used (snapshot)';
COMMENT ON COLUMN routing_decisions.chosen_level IS 'easy / hard';
COMMENT ON COLUMN routing_decisions.algorithm_version IS 'Routing algorithm version for reproducibility';
COMMENT ON COLUMN break_sessions.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN break_sessions.attempt_id IS 'Composite FK (attempt_id, user_id). ON DELETE CASCADE';
COMMENT ON COLUMN break_sessions.user_id IS 'Denormalised for RLS';
COMMENT ON COLUMN break_sessions.after_section_id IS 'ON DELETE RESTRICT';
COMMENT ON COLUMN break_sessions.ends_at IS 'Server-authoritative break end';
COMMENT ON COLUMN break_sessions.skipped_at IS 'Allowed only if test_sections.break_skippable';
COMMENT ON COLUMN answers.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN answers.module_attempt_id IS 'Composite FK (module_attempt_id, user_id). ON DELETE CASCADE';
COMMENT ON COLUMN answers.question_id IS 'ON DELETE RESTRICT. Unique with module_attempt_id.';
COMMENT ON COLUMN answers.user_id IS 'Denormalised for analytics and RLS';
COMMENT ON COLUMN answers.section IS 'Snapshot copied from question at first write';
COMMENT ON COLUMN answers.domain_id IS 'Snapshot copy (no FK; avoids write amplification)';
COMMENT ON COLUMN answers.skill_id IS 'Snapshot copy (no FK). Powers weakness queries without joins.';
COMMENT ON COLUMN answers.difficulty IS 'Snapshot of the question''s difficulty when served';
COMMENT ON COLUMN answers.selected_choice_id IS 'Composite FK (question_id, selected_choice_id). Multiple choice only.';
COMMENT ON COLUMN answers.response_text IS 'Grid-in only. Never both this and selected_choice_id.';
COMMENT ON COLUMN answers.eliminated_choice_ids IS 'Strike-through (answer eliminator) state';
COMMENT ON COLUMN answers.is_flagged IS 'Mark for review';
COMMENT ON COLUMN answers.is_correct IS 'NULL until graded server-side at module submit. Client value is never trusted.';
COMMENT ON COLUMN answers.time_spent_ms IS 'Accumulated time on the question';
COMMENT ON COLUMN answers.revision IS 'Optimistic concurrency counter; stale writes are rejected';
COMMENT ON COLUMN answers.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN answers.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN answer_events.id IS 'Composite PK with server_ts (partition key)';
COMMENT ON COLUMN answer_events.server_ts IS 'Partition key';
COMMENT ON COLUMN answer_events.module_attempt_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN answer_events.question_id IS 'No FK (append-only, write-optimised)';
COMMENT ON COLUMN answer_events.payload IS 'Event detail (choice label, etc.). Never queried relationally.';
COMMENT ON COLUMN answer_events.client_ts IS 'Client clock (informational only; never used for timing decisions)';
COMMENT ON COLUMN annotations.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN annotations.module_attempt_id IS 'Composite FK (module_attempt_id, user_id). ON DELETE CASCADE';
COMMENT ON COLUMN annotations.user_id IS 'Denormalised for RLS';
COMMENT ON COLUMN annotations.question_id IS 'ON DELETE RESTRICT';
COMMENT ON COLUMN annotations.target IS 'passage / stem';
COMMENT ON COLUMN annotations.color IS 'yellow / blue / pink';
COMMENT ON COLUMN annotations.note IS 'Max 2,000 characters';
COMMENT ON COLUMN annotations.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN annotations.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN score_reports.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN score_reports.attempt_id IS 'Composite FK (attempt_id, user_id). ON DELETE CASCADE';
COMMENT ON COLUMN score_reports.user_id IS 'Denormalised for RLS and history queries';
COMMENT ON COLUMN score_reports.rw_scaled IS '200-800';
COMMENT ON COLUMN score_reports.math_scaled IS '200-800';
COMMENT ON COLUMN score_reports.total_scaled IS '400-1600; must equal rw_scaled + math_scaled';
COMMENT ON COLUMN score_reports.rw_theta IS 'Optional IRT ability estimate';
COMMENT ON COLUMN score_reports.rw_stage2_level IS 'easy / hard path taken';
COMMENT ON COLUMN score_reports.scoring_version IS 'Scoring algorithm version for reproducibility';
COMMENT ON COLUMN score_reports.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN domain_results.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN domain_results.report_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN domain_results.domain_id IS 'ON DELETE RESTRICT';
COMMENT ON COLUMN domain_results.accuracy IS 'Percent 0-100';
COMMENT ON COLUMN skill_results.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN skill_results.report_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN skill_results.skill_id IS 'ON DELETE RESTRICT';
COMMENT ON COLUMN skill_results.domain_id IS 'Snapshot copy';
COMMENT ON COLUMN skill_results.accuracy IS 'Percent 0-100';
COMMENT ON COLUMN user_skill_stats.user_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN user_skill_stats.skill_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN user_skill_stats.accuracy_pct IS 'GENERATED ALWAYS AS (round(100.0 * total_correct / nullif(total_answered,0), 2)) STORED. Cannot drift.';
COMMENT ON COLUMN user_skill_stats.recent_accuracy IS 'Accuracy over the last N answers (N in recent_window)';
COMMENT ON COLUMN user_skill_stats.mastery IS '0-1 estimate (EWMA or Bayesian). Method documented in scoring_version of the job.';
COMMENT ON COLUMN user_skill_stats.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN user_domain_stats.user_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN user_domain_stats.domain_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN user_domain_stats.accuracy_pct IS 'GENERATED ALWAYS AS (...) STORED';
COMMENT ON COLUMN user_domain_stats.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN user_stats.user_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN user_stats.overall_accuracy IS 'GENERATED ALWAYS AS (...) STORED';
COMMENT ON COLUMN user_stats.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN question_stats.question_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN question_stats.accuracy_pct IS 'GENERATED ALWAYS AS (...) STORED';
COMMENT ON COLUMN question_stats.choice_distribution IS '{ ''A'': n, ''B'': n, ... } for distractor analysis';
COMMENT ON COLUMN question_stats.processed_through IS 'Watermark: answers up to this time are already counted (makes the batch job idempotent)';
COMMENT ON COLUMN question_stats.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN user_goals.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN user_goals.user_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN user_goals.skill_id IS 'ON DELETE CASCADE. NULL = overall goal';
COMMENT ON COLUMN user_goals.target_accuracy IS 'Percent, e.g. 80.00';
COMMENT ON COLUMN user_goals.target_score IS 'Optional scaled-score goal';
COMMENT ON COLUMN user_goals.created_at IS 'Row creation time (UTC)';
COMMENT ON COLUMN user_goals.updated_at IS 'Maintained by trigger trg_set_updated_at';
COMMENT ON COLUMN audit_logs.id IS 'Composite PK with created_at (partition key)';
COMMENT ON COLUMN audit_logs.created_at IS 'Partition key';
COMMENT ON COLUMN audit_logs.actor_user_id IS 'ON DELETE SET NULL';
COMMENT ON COLUMN audit_logs.action IS 'e.g. question.publish, user.role_change, attempt.void';
COMMENT ON COLUMN audit_logs.before_data IS 'Redacted: never contains secrets';
COMMENT ON COLUMN audit_logs.request_id IS 'Correlates with application logs';
COMMENT ON COLUMN data_requests.id IS 'UUIDv7 generated by the application (time-ordered, index-friendly)';
COMMENT ON COLUMN data_requests.user_id IS 'ON DELETE SET NULL (record survives account deletion)';
COMMENT ON COLUMN data_requests.request_type IS 'export / delete';
COMMENT ON COLUMN data_requests.export_asset_key IS 'Encrypted S3 object; signed URL expires in 24 h';
COMMENT ON COLUMN data_requests.expires_at IS 'Export file deleted after this time';
COMMENT ON COLUMN idempotency_keys.user_id IS 'ON DELETE CASCADE';
COMMENT ON COLUMN idempotency_keys.idem_key IS 'Client-generated key sent in Idempotency-Key header';
COMMENT ON COLUMN idempotency_keys.request_hash IS 'SHA-256 of request body; mismatch => 422';
COMMENT ON COLUMN idempotency_keys.created_at IS 'Row creation time (UTC)';

\echo === BUILD COMPLETE: 40 tables, 51 RLS policies, 8 domains, 29 skills ===
