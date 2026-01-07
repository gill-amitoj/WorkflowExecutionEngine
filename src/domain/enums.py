"""
Domain enums for workflow orchestration.

These enums define the possible states for workflows, steps, and executions.
The state machine logic enforces valid transitions between these states.
"""

from enum import Enum


class WorkflowStatus(str, Enum):
    """
    Status of a workflow definition.
    
    - DRAFT: Workflow is being designed, not yet ready for execution
    - ACTIVE: Workflow is ready to be executed
    - DEPRECATED: Workflow is no longer recommended for use
    - ARCHIVED: Workflow is archived and cannot be executed
    """
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ExecutionStatus(str, Enum):
    """
    Status of a workflow execution.
    
    State machine transitions:
    PENDING → RUNNING → COMPLETED (success path)
    PENDING → RUNNING → FAILED → RETRYING → RUNNING (retry path)
    PENDING → RUNNING → FAILED (after max retries)
    Any state → CANCELLED (manual intervention)
    
    - PENDING: Execution is queued and waiting to start
    - RUNNING: Execution is currently in progress
    - COMPLETED: Execution finished successfully
    - FAILED: Execution failed (may be retried)
    - RETRYING: Execution is scheduled for retry
    - CANCELLED: Execution was manually cancelled
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """
    Status of a workflow step execution.
    
    - PENDING: Step is waiting to be executed
    - RUNNING: Step is currently executing
    - COMPLETED: Step completed successfully
    - FAILED: Step failed
    - SKIPPED: Step was skipped (e.g., due to conditions)
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class LogLevel(str, Enum):
    """
    Log levels for execution logs.
    
    - DEBUG: Detailed debugging information
    - INFO: General information about execution
    - WARNING: Warning messages (non-fatal issues)
    - ERROR: Error messages (failures)
    """
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
