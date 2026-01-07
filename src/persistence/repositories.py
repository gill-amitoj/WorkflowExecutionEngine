"""
Repository implementations for data access.

These repositories provide a clean interface between the domain layer
and the persistence layer. They handle all SQL queries and data mapping.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.domain import (
    Workflow, WorkflowStep, WorkflowExecution, ExecutionLog,
    WorkflowStatus, ExecutionStatus, StepStatus, LogLevel
)
from src.domain.entities import StepExecution
from .database import Database

logger = logging.getLogger(__name__)


class WorkflowRepository:
    """Repository for workflow and workflow step persistence."""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create_workflow(self, workflow: Workflow) -> Workflow:
        """Create a new workflow."""
        query = """
            INSERT INTO workflows (id, name, description, status, version, metadata, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        params = (
            str(workflow.id),
            workflow.name,
            workflow.description,
            workflow.status.value,
            workflow.version,
            json.dumps(workflow.metadata),
            workflow.created_at,
            workflow.updated_at,
        )
        
        with self.db.transaction() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            
            # Create steps if any
            for step in workflow.steps:
                self._create_step(cur, step)
        
        return self._row_to_workflow(row, workflow.steps)
    
    def _create_step(self, cursor, step: WorkflowStep) -> None:
        """Create a workflow step (internal helper)."""
        query = """
            INSERT INTO workflow_steps 
            (id, workflow_id, name, task_type, step_order, config, timeout_seconds, max_retries, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            str(step.id),
            str(step.workflow_id),
            step.name,
            step.task_type,
            step.step_order,
            json.dumps(step.config),
            step.timeout_seconds,
            step.max_retries,
            step.created_at,
            step.updated_at,
        )
        cursor.execute(query, params)
    
    def add_step(self, step: WorkflowStep) -> WorkflowStep:
        """Add a step to an existing workflow."""
        query = """
            INSERT INTO workflow_steps 
            (id, workflow_id, name, task_type, step_order, config, timeout_seconds, max_retries, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        params = (
            str(step.id),
            str(step.workflow_id),
            step.name,
            step.task_type,
            step.step_order,
            json.dumps(step.config),
            step.timeout_seconds,
            step.max_retries,
            step.created_at,
            step.updated_at,
        )
        row = self.db.execute_one(query, params)
        return self._row_to_step(row)
    
    def get_workflow_by_id(self, workflow_id: UUID) -> Optional[Workflow]:
        """Get a workflow by ID with all its steps."""
        query = "SELECT * FROM workflows WHERE id = %s"
        row = self.db.execute_one(query, (str(workflow_id),))
        
        if not row:
            return None
        
        steps = self.get_steps_by_workflow_id(workflow_id)
        return self._row_to_workflow(row, steps)
    
    def get_workflow_by_name(self, name: str) -> Optional[Workflow]:
        """Get a workflow by name."""
        query = "SELECT * FROM workflows WHERE name = %s ORDER BY version DESC LIMIT 1"
        row = self.db.execute_one(query, (name,))
        
        if not row:
            return None
        
        workflow_id = UUID(row["id"])
        steps = self.get_steps_by_workflow_id(workflow_id)
        return self._row_to_workflow(row, steps)
    
    def get_steps_by_workflow_id(self, workflow_id: UUID) -> List[WorkflowStep]:
        """Get all steps for a workflow, ordered by step_order."""
        query = """
            SELECT * FROM workflow_steps 
            WHERE workflow_id = %s 
            ORDER BY step_order
        """
        rows = self.db.execute(query, (str(workflow_id),))
        return [self._row_to_step(row) for row in rows]
    
    def update_workflow_status(self, workflow_id: UUID, status: WorkflowStatus) -> bool:
        """Update workflow status."""
        query = """
            UPDATE workflows 
            SET status = %s, updated_at = %s 
            WHERE id = %s
        """
        self.db.execute(query, (status.value, datetime.utcnow(), str(workflow_id)))
        return True
    
    def list_workflows(
        self,
        status: Optional[WorkflowStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Workflow]:
        """List workflows with optional status filter."""
        if status:
            query = """
                SELECT * FROM workflows 
                WHERE status = %s 
                ORDER BY created_at DESC 
                LIMIT %s OFFSET %s
            """
            rows = self.db.execute(query, (status.value, limit, offset))
        else:
            query = """
                SELECT * FROM workflows 
                ORDER BY created_at DESC 
                LIMIT %s OFFSET %s
            """
            rows = self.db.execute(query, (limit, offset))
        
        workflows = []
        for row in rows:
            workflow_id = UUID(row["id"])
            steps = self.get_steps_by_workflow_id(workflow_id)
            workflows.append(self._row_to_workflow(row, steps))
        
        return workflows
    
    def _row_to_workflow(self, row: dict, steps: List[WorkflowStep]) -> Workflow:
        """Convert database row to Workflow entity."""
        metadata = row.get("metadata", {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        return Workflow(
            id=UUID(row["id"]),
            name=row["name"],
            description=row["description"] or "",
            status=WorkflowStatus(row["status"]),
            version=row["version"],
            steps=steps,
            metadata=metadata,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    
    def _row_to_step(self, row: dict) -> WorkflowStep:
        """Convert database row to WorkflowStep entity."""
        config = row.get("config", {})
        if isinstance(config, str):
            config = json.loads(config)
        
        return WorkflowStep(
            id=UUID(row["id"]),
            workflow_id=UUID(row["workflow_id"]),
            name=row["name"],
            task_type=row["task_type"],
            step_order=row["step_order"],
            config=config,
            timeout_seconds=row["timeout_seconds"],
            max_retries=row["max_retries"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ExecutionRepository:
    """Repository for workflow execution persistence."""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create_execution(self, execution: WorkflowExecution) -> WorkflowExecution:
        """Create a new workflow execution."""
        query = """
            INSERT INTO workflow_executions 
            (id, workflow_id, idempotency_key, status, current_step_order, retry_count, 
             max_retries, input_data, scheduled_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        params = (
            str(execution.id),
            str(execution.workflow_id),
            execution.idempotency_key,
            execution.status.value,
            execution.current_step_order,
            execution.retry_count,
            execution.max_retries,
            json.dumps(execution.input_data),
            execution.scheduled_at,
            execution.created_at,
            execution.updated_at,
        )
        row = self.db.execute_one(query, params)
        return self._row_to_execution(row)
    
    def get_execution_by_id(self, execution_id: UUID) -> Optional[WorkflowExecution]:
        """Get an execution by ID."""
        query = "SELECT * FROM workflow_executions WHERE id = %s"
        row = self.db.execute_one(query, (str(execution_id),))
        
        if not row:
            return None
        
        execution = self._row_to_execution(row)
        execution.step_executions = self.get_step_executions(execution_id)
        return execution
    
    def get_execution_by_idempotency_key(
        self,
        workflow_id: UUID,
        idempotency_key: str,
    ) -> Optional[WorkflowExecution]:
        """Get an execution by idempotency key."""
        query = """
            SELECT * FROM workflow_executions 
            WHERE workflow_id = %s AND idempotency_key = %s
        """
        row = self.db.execute_one(query, (str(workflow_id), idempotency_key))
        
        if not row:
            return None
        
        return self._row_to_execution(row)
    
    def update_execution_status(
        self,
        execution_id: UUID,
        status: ExecutionStatus,
        error_message: Optional[str] = None,
        current_step_order: Optional[int] = None,
    ) -> bool:
        """Update execution status and optionally other fields."""
        updates = ["status = %s", "updated_at = %s"]
        params = [status.value, datetime.utcnow()]
        
        if error_message is not None:
            updates.append("error_message = %s")
            params.append(error_message)
        
        if current_step_order is not None:
            updates.append("current_step_order = %s")
            params.append(current_step_order)
        
        if status == ExecutionStatus.RUNNING:
            updates.append("started_at = COALESCE(started_at, %s)")
            params.append(datetime.utcnow())
        elif status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
            updates.append("completed_at = %s")
            params.append(datetime.utcnow())
        
        params.append(str(execution_id))
        
        query = f"""
            UPDATE workflow_executions 
            SET {', '.join(updates)}
            WHERE id = %s
        """
        self.db.execute(query, tuple(params))
        return True
    
    def increment_retry_count(self, execution_id: UUID) -> int:
        """Increment retry count and return new value."""
        query = """
            UPDATE workflow_executions 
            SET retry_count = retry_count + 1, updated_at = %s
            WHERE id = %s
            RETURNING retry_count
        """
        row = self.db.execute_one(query, (datetime.utcnow(), str(execution_id)))
        return row["retry_count"] if row else 0
    
    def set_output_data(self, execution_id: UUID, output_data: Dict[str, Any]) -> bool:
        """Set the output data for an execution."""
        query = """
            UPDATE workflow_executions 
            SET output_data = %s, updated_at = %s
            WHERE id = %s
        """
        self.db.execute(query, (json.dumps(output_data), datetime.utcnow(), str(execution_id)))
        return True
    
    def create_step_execution(self, step_exec: StepExecution) -> StepExecution:
        """Create a new step execution."""
        query = """
            INSERT INTO step_executions 
            (id, execution_id, step_id, step_order, status, attempt_number, input_data, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        params = (
            str(step_exec.id),
            str(step_exec.execution_id),
            str(step_exec.step_id),
            step_exec.step_order,
            step_exec.status.value,
            step_exec.attempt_number,
            json.dumps(step_exec.input_data),
            step_exec.created_at,
            step_exec.updated_at,
        )
        row = self.db.execute_one(query, params)
        return self._row_to_step_execution(row)
    
    def update_step_execution(
        self,
        step_exec_id: UUID,
        status: StepStatus,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        error_details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update step execution status and data."""
        updates = ["status = %s", "updated_at = %s"]
        params = [status.value, datetime.utcnow()]
        
        if output_data is not None:
            updates.append("output_data = %s")
            params.append(json.dumps(output_data))
        
        if error_message is not None:
            updates.append("error_message = %s")
            params.append(error_message)
        
        if error_details is not None:
            updates.append("error_details = %s")
            params.append(json.dumps(error_details))
        
        if status == StepStatus.RUNNING:
            updates.append("started_at = %s")
            params.append(datetime.utcnow())
        elif status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED):
            updates.append("completed_at = %s")
            params.append(datetime.utcnow())
        
        params.append(str(step_exec_id))
        
        query = f"""
            UPDATE step_executions 
            SET {', '.join(updates)}
            WHERE id = %s
        """
        self.db.execute(query, tuple(params))
        return True
    
    def get_step_executions(self, execution_id: UUID) -> List[StepExecution]:
        """Get all step executions for an execution."""
        query = """
            SELECT * FROM step_executions 
            WHERE execution_id = %s 
            ORDER BY step_order, attempt_number
        """
        rows = self.db.execute(query, (str(execution_id),))
        return [self._row_to_step_execution(row) for row in rows]
    
    def list_executions(
        self,
        workflow_id: Optional[UUID] = None,
        status: Optional[ExecutionStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[WorkflowExecution]:
        """List executions with optional filters."""
        conditions = []
        params = []
        
        if workflow_id:
            conditions.append("workflow_id = %s")
            params.append(str(workflow_id))
        
        if status:
            conditions.append("status = %s")
            params.append(status.value)
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        query = f"""
            SELECT * FROM workflow_executions 
            {where_clause}
            ORDER BY created_at DESC 
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        
        rows = self.db.execute(query, tuple(params))
        return [self._row_to_execution(row) for row in rows]
    
    def get_pending_executions(self, limit: int = 100) -> List[WorkflowExecution]:
        """Get executions that are pending and ready to run."""
        query = """
            SELECT * FROM workflow_executions 
            WHERE status = %s 
            AND (scheduled_at IS NULL OR scheduled_at <= %s)
            ORDER BY created_at 
            LIMIT %s
        """
        rows = self.db.execute(query, (ExecutionStatus.PENDING.value, datetime.utcnow(), limit))
        return [self._row_to_execution(row) for row in rows]
    
    def _row_to_execution(self, row: dict) -> WorkflowExecution:
        """Convert database row to WorkflowExecution entity."""
        input_data = row.get("input_data", {})
        if isinstance(input_data, str):
            input_data = json.loads(input_data)
        
        output_data = row.get("output_data")
        if isinstance(output_data, str):
            output_data = json.loads(output_data)
        
        return WorkflowExecution(
            id=UUID(row["id"]),
            workflow_id=UUID(row["workflow_id"]),
            idempotency_key=row["idempotency_key"],
            status=ExecutionStatus(row["status"]),
            current_step_order=row["current_step_order"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            input_data=input_data,
            output_data=output_data,
            error_message=row.get("error_message"),
            scheduled_at=row.get("scheduled_at"),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    
    def _row_to_step_execution(self, row: dict) -> StepExecution:
        """Convert database row to StepExecution entity."""
        input_data = row.get("input_data", {})
        if isinstance(input_data, str):
            input_data = json.loads(input_data)
        
        output_data = row.get("output_data")
        if isinstance(output_data, str):
            output_data = json.loads(output_data)
        
        error_details = row.get("error_details")
        if isinstance(error_details, str):
            error_details = json.loads(error_details)
        
        return StepExecution(
            id=UUID(row["id"]),
            execution_id=UUID(row["execution_id"]),
            step_id=UUID(row["step_id"]),
            step_order=row["step_order"],
            status=StepStatus(row["status"]),
            attempt_number=row["attempt_number"],
            input_data=input_data,
            output_data=output_data,
            error_message=row.get("error_message"),
            error_details=error_details,
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class LogRepository:
    """Repository for execution logs."""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create_log(self, log: ExecutionLog) -> ExecutionLog:
        """Create a new execution log entry."""
        query = """
            INSERT INTO execution_logs 
            (id, execution_id, step_execution_id, level, message, details, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        params = (
            str(log.id),
            str(log.execution_id),
            str(log.step_execution_id) if log.step_execution_id else None,
            log.level.value,
            log.message,
            json.dumps(log.details),
            log.timestamp,
        )
        row = self.db.execute_one(query, params)
        return self._row_to_log(row)
    
    def get_logs_by_execution_id(
        self,
        execution_id: UUID,
        level: Optional[LogLevel] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[ExecutionLog]:
        """Get logs for an execution."""
        if level:
            query = """
                SELECT * FROM execution_logs 
                WHERE execution_id = %s AND level = %s
                ORDER BY timestamp 
                LIMIT %s OFFSET %s
            """
            rows = self.db.execute(query, (str(execution_id), level.value, limit, offset))
        else:
            query = """
                SELECT * FROM execution_logs 
                WHERE execution_id = %s 
                ORDER BY timestamp 
                LIMIT %s OFFSET %s
            """
            rows = self.db.execute(query, (str(execution_id), limit, offset))
        
        return [self._row_to_log(row) for row in rows]
    
    def get_logs_by_step_execution_id(
        self,
        step_execution_id: UUID,
    ) -> List[ExecutionLog]:
        """Get logs for a specific step execution."""
        query = """
            SELECT * FROM execution_logs 
            WHERE step_execution_id = %s 
            ORDER BY timestamp
        """
        rows = self.db.execute(query, (str(step_execution_id),))
        return [self._row_to_log(row) for row in rows]
    
    def _row_to_log(self, row: dict) -> ExecutionLog:
        """Convert database row to ExecutionLog entity."""
        details = row.get("details", {})
        if isinstance(details, str):
            details = json.loads(details)
        
        step_execution_id = row.get("step_execution_id")
        
        return ExecutionLog(
            id=UUID(row["id"]),
            execution_id=UUID(row["execution_id"]),
            step_execution_id=UUID(step_execution_id) if step_execution_id else None,
            level=LogLevel(row["level"]),
            message=row["message"],
            details=details,
            timestamp=row["timestamp"],
        )
