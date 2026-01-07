-- Workflow Orchestration Engine Database Schema
-- PostgreSQL

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- WORKFLOWS TABLE
-- Stores workflow definitions (templates)
-- ============================================
CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    version INTEGER NOT NULL DEFAULT 1,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT workflows_status_check CHECK (status IN ('draft', 'active', 'deprecated', 'archived')),
    CONSTRAINT workflows_name_version_unique UNIQUE (name, version)
);

-- Indexes for workflows
CREATE INDEX idx_workflows_status ON workflows(status);
CREATE INDEX idx_workflows_name ON workflows(name);
CREATE INDEX idx_workflows_created_at ON workflows(created_at DESC);

-- ============================================
-- WORKFLOW STEPS TABLE
-- Stores individual steps within a workflow
-- ============================================
CREATE TABLE workflow_steps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    task_type VARCHAR(100) NOT NULL,
    step_order INTEGER NOT NULL,
    config JSONB DEFAULT '{}',
    timeout_seconds INTEGER DEFAULT 300,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT workflow_steps_order_unique UNIQUE (workflow_id, step_order),
    CONSTRAINT workflow_steps_timeout_positive CHECK (timeout_seconds > 0),
    CONSTRAINT workflow_steps_retries_non_negative CHECK (max_retries >= 0)
);

-- Indexes for workflow_steps
CREATE INDEX idx_workflow_steps_workflow_id ON workflow_steps(workflow_id);
CREATE INDEX idx_workflow_steps_task_type ON workflow_steps(task_type);

-- ============================================
-- WORKFLOW EXECUTIONS TABLE
-- Stores execution instances of workflows
-- ============================================
CREATE TABLE workflow_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE RESTRICT,
    idempotency_key VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    current_step_order INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    input_data JSONB DEFAULT '{}',
    output_data JSONB,
    error_message TEXT,
    scheduled_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT workflow_executions_status_check CHECK (
        status IN ('pending', 'running', 'completed', 'failed', 'retrying', 'cancelled')
    ),
    CONSTRAINT workflow_executions_idempotency_unique UNIQUE (workflow_id, idempotency_key),
    CONSTRAINT workflow_executions_retries_non_negative CHECK (retry_count >= 0)
);

-- Indexes for workflow_executions
CREATE INDEX idx_workflow_executions_workflow_id ON workflow_executions(workflow_id);
CREATE INDEX idx_workflow_executions_status ON workflow_executions(status);
CREATE INDEX idx_workflow_executions_idempotency ON workflow_executions(workflow_id, idempotency_key);
CREATE INDEX idx_workflow_executions_created_at ON workflow_executions(created_at DESC);
CREATE INDEX idx_workflow_executions_scheduled ON workflow_executions(scheduled_at) 
    WHERE status = 'pending' AND scheduled_at IS NOT NULL;

-- Partial index for finding pending executions efficiently
CREATE INDEX idx_workflow_executions_pending ON workflow_executions(created_at) 
    WHERE status = 'pending';

-- ============================================
-- STEP EXECUTIONS TABLE
-- Stores execution state for individual steps
-- ============================================
CREATE TABLE step_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    execution_id UUID NOT NULL REFERENCES workflow_executions(id) ON DELETE CASCADE,
    step_id UUID NOT NULL REFERENCES workflow_steps(id) ON DELETE RESTRICT,
    step_order INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    attempt_number INTEGER DEFAULT 1,
    input_data JSONB DEFAULT '{}',
    output_data JSONB,
    error_message TEXT,
    error_details JSONB,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT step_executions_status_check CHECK (
        status IN ('pending', 'running', 'completed', 'failed', 'skipped')
    ),
    CONSTRAINT step_executions_attempt_positive CHECK (attempt_number > 0)
);

-- Indexes for step_executions
CREATE INDEX idx_step_executions_execution_id ON step_executions(execution_id);
CREATE INDEX idx_step_executions_step_id ON step_executions(step_id);
CREATE INDEX idx_step_executions_status ON step_executions(status);

-- ============================================
-- EXECUTION LOGS TABLE
-- Stores detailed audit logs for executions
-- ============================================
CREATE TABLE execution_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    execution_id UUID NOT NULL REFERENCES workflow_executions(id) ON DELETE CASCADE,
    step_execution_id UUID REFERENCES step_executions(id) ON DELETE CASCADE,
    level VARCHAR(20) NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT execution_logs_level_check CHECK (
        level IN ('debug', 'info', 'warning', 'error')
    )
);

-- Indexes for execution_logs
CREATE INDEX idx_execution_logs_execution_id ON execution_logs(execution_id);
CREATE INDEX idx_execution_logs_step_execution_id ON execution_logs(step_execution_id);
CREATE INDEX idx_execution_logs_level ON execution_logs(level);
CREATE INDEX idx_execution_logs_timestamp ON execution_logs(timestamp DESC);

-- Composite index for common query pattern
CREATE INDEX idx_execution_logs_execution_timestamp ON execution_logs(execution_id, timestamp);

-- ============================================
-- FUNCTIONS AND TRIGGERS
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_workflows_updated_at
    BEFORE UPDATE ON workflows
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workflow_steps_updated_at
    BEFORE UPDATE ON workflow_steps
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workflow_executions_updated_at
    BEFORE UPDATE ON workflow_executions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_step_executions_updated_at
    BEFORE UPDATE ON step_executions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================

COMMENT ON TABLE workflows IS 'Workflow definitions/templates';
COMMENT ON TABLE workflow_steps IS 'Individual steps within a workflow';
COMMENT ON TABLE workflow_executions IS 'Instances of workflow executions';
COMMENT ON TABLE step_executions IS 'Execution state for individual steps';
COMMENT ON TABLE execution_logs IS 'Audit logs for workflow executions';

COMMENT ON COLUMN workflow_executions.idempotency_key IS 'Unique key to prevent duplicate executions';
COMMENT ON COLUMN workflow_executions.current_step_order IS 'Track progress for resumability';
COMMENT ON COLUMN workflow_steps.task_type IS 'Handler type: http_request, data_transform, notification, etc.';
