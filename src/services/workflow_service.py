"""
Workflow service for managing workflow definitions.

Handles CRUD operations and validation for workflows and their steps.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.domain import (
    Workflow, WorkflowStep, WorkflowStatus
)
from src.persistence import WorkflowRepository


logger = logging.getLogger(__name__)


class WorkflowServiceError(Exception):
    """Base exception for workflow service errors."""
    pass


class WorkflowNotFoundError(WorkflowServiceError):
    """Raised when a workflow is not found."""
    pass


class WorkflowValidationError(WorkflowServiceError):
    """Raised when workflow validation fails."""
    pass


class WorkflowService:
    """
    Service for managing workflow definitions.
    
    Provides business logic for creating, updating, and managing workflows.
    """
    
    def __init__(self, workflow_repo: WorkflowRepository):
        self.workflow_repo = workflow_repo
    
    def create_workflow(
        self,
        name: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Workflow:
        """
        Create a new workflow definition.
        
        The workflow is created in DRAFT status.
        """
        logger.info(f"Creating workflow: {name}")
        
        # Validate name
        if not name or not name.strip():
            raise WorkflowValidationError("Workflow name is required")
        
        # Check for existing workflow with same name
        existing = self.workflow_repo.get_workflow_by_name(name)
        if existing:
            raise WorkflowValidationError(f"Workflow with name '{name}' already exists")
        
        workflow = Workflow.create(
            name=name.strip(),
            description=description,
            metadata=metadata,
        )
        
        return self.workflow_repo.create_workflow(workflow)
    
    def add_step(
        self,
        workflow_id: UUID,
        name: str,
        task_type: str,
        step_order: int,
        config: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 300,
        max_retries: int = 3,
    ) -> WorkflowStep:
        """
        Add a step to a workflow.
        
        Only works for workflows in DRAFT status.
        """
        workflow = self.get_workflow(workflow_id)
        
        if workflow.status != WorkflowStatus.DRAFT:
            raise WorkflowValidationError(
                f"Cannot add steps to workflow in {workflow.status.value} status"
            )
        
        # Validate step
        if not name or not name.strip():
            raise WorkflowValidationError("Step name is required")
        
        if not task_type or not task_type.strip():
            raise WorkflowValidationError("Task type is required")
        
        if step_order < 0:
            raise WorkflowValidationError("Step order must be non-negative")
        
        # Check for duplicate step order
        existing_orders = {s.step_order for s in workflow.steps}
        if step_order in existing_orders:
            raise WorkflowValidationError(f"Step order {step_order} already exists")
        
        step = WorkflowStep.create(
            workflow_id=workflow_id,
            name=name.strip(),
            task_type=task_type.strip(),
            step_order=step_order,
            config=config,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        
        logger.info(f"Adding step '{name}' to workflow {workflow_id}")
        return self.workflow_repo.add_step(step)
    
    def get_workflow(self, workflow_id: UUID) -> Workflow:
        """Get a workflow by ID."""
        workflow = self.workflow_repo.get_workflow_by_id(workflow_id)
        
        if not workflow:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")
        
        return workflow
    
    def get_workflow_by_name(self, name: str) -> Workflow:
        """Get a workflow by name."""
        workflow = self.workflow_repo.get_workflow_by_name(name)
        
        if not workflow:
            raise WorkflowNotFoundError(f"Workflow '{name}' not found")
        
        return workflow
    
    def activate_workflow(self, workflow_id: UUID) -> Workflow:
        """
        Activate a workflow for execution.
        
        Validates that the workflow has at least one step.
        """
        workflow = self.get_workflow(workflow_id)
        
        if workflow.status != WorkflowStatus.DRAFT:
            raise WorkflowValidationError(
                f"Can only activate workflows in DRAFT status, current: {workflow.status.value}"
            )
        
        if not workflow.steps:
            raise WorkflowValidationError("Cannot activate workflow without steps")
        
        # Validate step orders are sequential
        step_orders = sorted(s.step_order for s in workflow.steps)
        expected = list(range(step_orders[0], step_orders[0] + len(step_orders)))
        if step_orders != expected:
            raise WorkflowValidationError("Step orders must be sequential")
        
        logger.info(f"Activating workflow {workflow_id}")
        self.workflow_repo.update_workflow_status(workflow_id, WorkflowStatus.ACTIVE)
        
        workflow.status = WorkflowStatus.ACTIVE
        return workflow
    
    def deprecate_workflow(self, workflow_id: UUID) -> Workflow:
        """Mark a workflow as deprecated."""
        workflow = self.get_workflow(workflow_id)
        
        if workflow.status not in (WorkflowStatus.ACTIVE, WorkflowStatus.DRAFT):
            raise WorkflowValidationError(
                f"Cannot deprecate workflow in {workflow.status.value} status"
            )
        
        logger.info(f"Deprecating workflow {workflow_id}")
        self.workflow_repo.update_workflow_status(workflow_id, WorkflowStatus.DEPRECATED)
        
        workflow.status = WorkflowStatus.DEPRECATED
        return workflow
    
    def archive_workflow(self, workflow_id: UUID) -> Workflow:
        """Archive a workflow."""
        workflow = self.get_workflow(workflow_id)
        
        logger.info(f"Archiving workflow {workflow_id}")
        self.workflow_repo.update_workflow_status(workflow_id, WorkflowStatus.ARCHIVED)
        
        workflow.status = WorkflowStatus.ARCHIVED
        return workflow
    
    def list_workflows(
        self,
        status: Optional[WorkflowStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Workflow]:
        """List workflows with optional filtering."""
        return self.workflow_repo.list_workflows(status=status, limit=limit, offset=offset)
