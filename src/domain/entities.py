"""
Domain entities for workflow orchestration.

These are the core domain objects that represent workflows, steps,
executions, and logs. They are independent of any persistence mechanism.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from .enums import WorkflowStatus, ExecutionStatus, StepStatus, LogLevel


@dataclass
class WorkflowStep:
    """
    Represents a single step in a workflow definition.
    
    Steps are executed in order (by step_order).
    Each step has a task type that determines which handler processes it.
    """
    id: UUID
    workflow_id: UUID
    name: str
    task_type: str  # e.g., "http_request", "data_transform", "notification"
    step_order: int
    config: Dict[str, Any] = field(default_factory=dict)  # Step-specific configuration
    timeout_seconds: int = 300  # Default 5 minute timeout per step
    max_retries: int = 3
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @classmethod
    def create(
        cls,
        workflow_id: UUID,
        name: str,
        task_type: str,
        step_order: int,
        config: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 300,
        max_retries: int = 3,
    ) -> "WorkflowStep":
        """Factory method to create a new workflow step."""
        now = datetime.utcnow()
        return cls(
            id=uuid4(),
            workflow_id=workflow_id,
            name=name,
            task_type=task_type,
            step_order=step_order,
            config=config or {},
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            created_at=now,
            updated_at=now,
        )


@dataclass
class Workflow:
    """
    Represents a workflow definition.
    
    A workflow is a template that defines what steps to execute.
    Multiple executions can be created from a single workflow definition.
    """
    id: UUID
    name: str
    description: str
    status: WorkflowStatus
    version: int = 1
    steps: List[WorkflowStep] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @classmethod
    def create(
        cls,
        name: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Workflow":
        """Factory method to create a new workflow in DRAFT status."""
        now = datetime.utcnow()
        return cls(
            id=uuid4(),
            name=name,
            description=description,
            status=WorkflowStatus.DRAFT,
            version=1,
            steps=[],
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
    
    def add_step(self, step: WorkflowStep) -> None:
        """Add a step to the workflow."""
        self.steps.append(step)
        self.steps.sort(key=lambda s: s.step_order)
        self.updated_at = datetime.utcnow()
    
    def activate(self) -> None:
        """Activate the workflow for execution."""
        if self.status != WorkflowStatus.DRAFT:
            raise ValueError(f"Cannot activate workflow in {self.status} status")
        if not self.steps:
            raise ValueError("Cannot activate workflow without steps")
        self.status = WorkflowStatus.ACTIVE
        self.updated_at = datetime.utcnow()
    
    def deprecate(self) -> None:
        """Mark workflow as deprecated."""
        if self.status not in (WorkflowStatus.ACTIVE, WorkflowStatus.DRAFT):
            raise ValueError(f"Cannot deprecate workflow in {self.status} status")
        self.status = WorkflowStatus.DEPRECATED
        self.updated_at = datetime.utcnow()
    
    def archive(self) -> None:
        """Archive the workflow."""
        self.status = WorkflowStatus.ARCHIVED
        self.updated_at = datetime.utcnow()


@dataclass
class StepExecution:
    """
    Represents the execution state of a single step.
    
    Tracks the progress, output, and errors for one step in an execution.
    """
    id: UUID
    execution_id: UUID
    step_id: UUID
    step_order: int
    status: StepStatus
    attempt_number: int = 1
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @classmethod
    def create(
        cls,
        execution_id: UUID,
        step_id: UUID,
        step_order: int,
        input_data: Optional[Dict[str, Any]] = None,
    ) -> "StepExecution":
        """Factory method to create a new step execution."""
        now = datetime.utcnow()
        return cls(
            id=uuid4(),
            execution_id=execution_id,
            step_id=step_id,
            step_order=step_order,
            status=StepStatus.PENDING,
            input_data=input_data or {},
            created_at=now,
            updated_at=now,
        )
    
    def start(self) -> None:
        """Mark step as running."""
        self.status = StepStatus.RUNNING
        self.started_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def complete(self, output_data: Optional[Dict[str, Any]] = None) -> None:
        """Mark step as completed."""
        self.status = StepStatus.COMPLETED
        self.output_data = output_data
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def fail(self, error_message: str, error_details: Optional[Dict[str, Any]] = None) -> None:
        """Mark step as failed."""
        self.status = StepStatus.FAILED
        self.error_message = error_message
        self.error_details = error_details
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


@dataclass
class WorkflowExecution:
    """
    Represents a single execution of a workflow.
    
    Tracks the overall execution state, including which step is current,
    retry count, and timing information.
    """
    id: UUID
    workflow_id: UUID
    idempotency_key: str  # Prevents duplicate executions
    status: ExecutionStatus
    current_step_order: int = 0
    retry_count: int = 0
    max_retries: int = 3
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    step_executions: List[StepExecution] = field(default_factory=list)
    scheduled_at: Optional[datetime] = None  # For scheduled/delayed execution
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @classmethod
    def create(
        cls,
        workflow_id: UUID,
        idempotency_key: str,
        input_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        scheduled_at: Optional[datetime] = None,
    ) -> "WorkflowExecution":
        """Factory method to create a new workflow execution."""
        now = datetime.utcnow()
        return cls(
            id=uuid4(),
            workflow_id=workflow_id,
            idempotency_key=idempotency_key,
            status=ExecutionStatus.PENDING,
            input_data=input_data or {},
            max_retries=max_retries,
            scheduled_at=scheduled_at,
            created_at=now,
            updated_at=now,
        )
    
    @property
    def is_terminal(self) -> bool:
        """Check if execution is in a terminal state."""
        return self.status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        )
    
    @property
    def can_retry(self) -> bool:
        """Check if execution can be retried."""
        return (
            self.status == ExecutionStatus.FAILED
            and self.retry_count < self.max_retries
        )


@dataclass
class ExecutionLog:
    """
    Represents an audit log entry for a workflow execution.
    
    Provides detailed tracking of every significant event during execution.
    """
    id: UUID
    execution_id: UUID
    step_execution_id: Optional[UUID]  # Null for workflow-level logs
    level: LogLevel
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @classmethod
    def create(
        cls,
        execution_id: UUID,
        level: LogLevel,
        message: str,
        step_execution_id: Optional[UUID] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> "ExecutionLog":
        """Factory method to create a new execution log."""
        return cls(
            id=uuid4(),
            execution_id=execution_id,
            step_execution_id=step_execution_id,
            level=level,
            message=message,
            details=details or {},
            timestamp=datetime.utcnow(),
        )
    
    @classmethod
    def info(cls, execution_id: UUID, message: str, **details) -> "ExecutionLog":
        """Create an INFO level log."""
        return cls.create(execution_id, LogLevel.INFO, message, details=details)
    
    @classmethod
    def error(
        cls,
        execution_id: UUID,
        message: str,
        step_execution_id: Optional[UUID] = None,
        **details,
    ) -> "ExecutionLog":
        """Create an ERROR level log."""
        return cls.create(
            execution_id, LogLevel.ERROR, message,
            step_execution_id=step_execution_id, details=details
        )
