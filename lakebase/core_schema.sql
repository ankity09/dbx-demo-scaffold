-- Core Lakebase schema — required by scaffold core modules.
-- These 3 tables support notes, agent action tracking, and workflow management.
-- Apply this BEFORE domain_schema.sql.

-- ============================================================
-- Table: notes
-- Free-text notes attached to any domain entity
-- ============================================================
CREATE TABLE IF NOT EXISTS notes (
    note_id     SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id   VARCHAR(50) NOT NULL,
    note_text   TEXT NOT NULL,
    author      VARCHAR(100) NOT NULL DEFAULT 'system',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notes_entity ON notes(entity_type, entity_id);

-- ============================================================
-- Table: agent_actions
-- Autonomous agent actions from proactive monitoring
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_actions (
    action_id       SERIAL PRIMARY KEY,
    action_type     VARCHAR(50) NOT NULL,
    severity        VARCHAR(20) NOT NULL DEFAULT 'medium'
                    CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    entity_type     VARCHAR(50),
    entity_id       VARCHAR(50),
    description     TEXT NOT NULL,
    action_taken    TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'executed', 'dismissed', 'failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_actions_status ON agent_actions(status);
CREATE INDEX IF NOT EXISTS idx_agent_actions_type ON agent_actions(action_type);

-- ============================================================
-- Table: workflows
-- Multi-step autonomous workflow executions
-- ============================================================
CREATE TABLE IF NOT EXISTS workflows (
    workflow_id     SERIAL PRIMARY KEY,
    workflow_type   VARCHAR(50) NOT NULL,
    trigger_source  VARCHAR(30) NOT NULL DEFAULT 'monitor'
                    CHECK (trigger_source IN ('monitor', 'chat', 'manual')),
    severity        VARCHAR(20) NOT NULL DEFAULT 'medium',
    summary         TEXT NOT NULL,
    reasoning_chain JSONB NOT NULL DEFAULT '[]',
    entity_type     VARCHAR(50),
    entity_id       VARCHAR(50),
    status          VARCHAR(20) NOT NULL DEFAULT 'in_progress'
                    CHECK (status IN ('in_progress', 'pending_approval', 'approved', 'dismissed', 'failed')),
    result_data     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status);
CREATE INDEX IF NOT EXISTS idx_workflows_type ON workflows(workflow_type);

-- ============================================================
-- Grants — ensure app service principal can access all tables
-- ============================================================
GRANT ALL ON ALL TABLES IN SCHEMA public TO PUBLIC;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO PUBLIC;
