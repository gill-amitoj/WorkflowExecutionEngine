"""
Unit tests for workflow service.
"""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.domain import Workflow, WorkflowStep, WorkflowStatus
from src.services.workflow_service import (
    WorkflowService,
    WorkflowNotFoundError,
    WorkflowValidationError,
)


class TestWorkflowService:
    """Tests for WorkflowService."""
    
    @pytest.fixture
    def mock_repo(self):
        """Create a mock repository."""
        return MagicMock()
    
    @pytest.fixture
    def service(self, mock_repo):
        """Create service with mock repository."""
        return WorkflowService(mock_repo)
    
    def test_create_workflow(self, service, mock_repo):
        """Test workflow creation."""
        mock_repo.get_workflow_by_name.return_value = None
        mock_repo.create_workflow.side_effect = lambda w: w
        
        workflow = service.create_workflow(
            name="test-workflow",
            description="Test description",
            metadata={"owner": "test"},
        )
        
        assert workflow.name == "test-workflow"
        assert workflow.description == "Test description"
        assert workflow.status == WorkflowStatus.DRAFT
        mock_repo.create_workflow.assert_called_once()
    
    def test_create_workflow_empty_name(self, service):
        """Test that empty name raises error."""
        with pytest.raises(WorkflowValidationError, match="name is required"):
            service.create_workflow(name="", description="Test")
    
    def test_create_workflow_whitespace_name(self, service):
        """Test that whitespace-only name raises error."""
        with pytest.raises(WorkflowValidationError, match="name is required"):
            service.create_workflow(name="   ", description="Test")
    
    def test_create_workflow_duplicate_name(self, service, mock_repo):
        """Test that duplicate name raises error."""
        existing_workflow = Workflow.create(name="existing")
        mock_repo.get_workflow_by_name.return_value = existing_workflow
        
        with pytest.raises(WorkflowValidationError, match="already exists"):
            service.create_workflow(name="existing", description="Test")
    
    def test_add_step(self, service, mock_repo):
        """Test adding a step to a workflow."""
        workflow = Workflow.create(name="test")
        mock_repo.get_workflow_by_id.return_value = workflow
        mock_repo.add_step.side_effect = lambda s: s
        
        step = service.add_step(
            workflow_id=workflow.id,
            name="step1",
            task_type="log",
            step_order=0,
            config={"message": "test"},
        )
        
        assert step.name == "step1"
        assert step.task_type == "log"
        mock_repo.add_step.assert_called_once()
    
    def test_add_step_to_non_draft_workflow(self, service, mock_repo):
        """Test that steps cannot be added to non-draft workflows."""
        workflow = Workflow.create(name="test")
        workflow.status = WorkflowStatus.ACTIVE
        mock_repo.get_workflow_by_id.return_value = workflow
        
        with pytest.raises(WorkflowValidationError, match="Cannot add steps"):
            service.add_step(
                workflow_id=workflow.id,
                name="step1",
                task_type="log",
                step_order=0,
            )
    
    def test_add_step_empty_name(self, service, mock_repo):
        """Test that step with empty name raises error."""
        workflow = Workflow.create(name="test")
        mock_repo.get_workflow_by_id.return_value = workflow
        
        with pytest.raises(WorkflowValidationError, match="Step name is required"):
            service.add_step(
                workflow_id=workflow.id,
                name="",
                task_type="log",
                step_order=0,
            )
    
    def test_add_step_duplicate_order(self, service, mock_repo):
        """Test that duplicate step order raises error."""
        workflow = Workflow.create(name="test")
        existing_step = WorkflowStep.create(
            workflow_id=workflow.id,
            name="existing",
            task_type="log",
            step_order=0,
        )
        workflow.steps = [existing_step]
        mock_repo.get_workflow_by_id.return_value = workflow
        
        with pytest.raises(WorkflowValidationError, match="already exists"):
            service.add_step(
                workflow_id=workflow.id,
                name="new",
                task_type="log",
                step_order=0,
            )
    
    def test_get_workflow(self, service, mock_repo):
        """Test getting a workflow."""
        workflow = Workflow.create(name="test")
        mock_repo.get_workflow_by_id.return_value = workflow
        
        result = service.get_workflow(workflow.id)
        
        assert result == workflow
    
    def test_get_workflow_not_found(self, service, mock_repo):
        """Test getting non-existent workflow."""
        mock_repo.get_workflow_by_id.return_value = None
        
        with pytest.raises(WorkflowNotFoundError):
            service.get_workflow(uuid4())
    
    def test_activate_workflow(self, service, mock_repo):
        """Test workflow activation."""
        workflow = Workflow.create(name="test")
        step = WorkflowStep.create(
            workflow_id=workflow.id,
            name="step1",
            task_type="log",
            step_order=0,
        )
        workflow.steps = [step]
        mock_repo.get_workflow_by_id.return_value = workflow
        mock_repo.update_workflow_status.return_value = True
        
        result = service.activate_workflow(workflow.id)
        
        assert result.status == WorkflowStatus.ACTIVE
        mock_repo.update_workflow_status.assert_called_once()
    
    def test_activate_workflow_without_steps(self, service, mock_repo):
        """Test that workflow without steps cannot be activated."""
        workflow = Workflow.create(name="test")
        workflow.steps = []
        mock_repo.get_workflow_by_id.return_value = workflow
        
        with pytest.raises(WorkflowValidationError, match="without steps"):
            service.activate_workflow(workflow.id)
    
    def test_activate_non_draft_workflow(self, service, mock_repo):
        """Test that non-draft workflow cannot be activated."""
        workflow = Workflow.create(name="test")
        workflow.status = WorkflowStatus.ARCHIVED
        mock_repo.get_workflow_by_id.return_value = workflow
        
        with pytest.raises(WorkflowValidationError, match="DRAFT status"):
            service.activate_workflow(workflow.id)
    
    def test_activate_workflow_non_sequential_steps(self, service, mock_repo):
        """Test that workflow with non-sequential steps cannot be activated."""
        workflow = Workflow.create(name="test")
        step1 = WorkflowStep.create(
            workflow_id=workflow.id,
            name="step1",
            task_type="log",
            step_order=0,
        )
        step2 = WorkflowStep.create(
            workflow_id=workflow.id,
            name="step2",
            task_type="log",
            step_order=5,  # Non-sequential
        )
        workflow.steps = [step1, step2]
        mock_repo.get_workflow_by_id.return_value = workflow
        
        with pytest.raises(WorkflowValidationError, match="sequential"):
            service.activate_workflow(workflow.id)
    
    def test_deprecate_workflow(self, service, mock_repo):
        """Test workflow deprecation."""
        workflow = Workflow.create(name="test")
        workflow.status = WorkflowStatus.ACTIVE
        mock_repo.get_workflow_by_id.return_value = workflow
        mock_repo.update_workflow_status.return_value = True
        
        result = service.deprecate_workflow(workflow.id)
        
        assert result.status == WorkflowStatus.DEPRECATED
    
    def test_list_workflows(self, service, mock_repo):
        """Test listing workflows."""
        workflows = [Workflow.create(name=f"test-{i}") for i in range(3)]
        mock_repo.list_workflows.return_value = workflows
        
        result = service.list_workflows(limit=10, offset=0)
        
        assert len(result) == 3
        mock_repo.list_workflows.assert_called_once_with(
            status=None, limit=10, offset=0
        )
    
    def test_list_workflows_with_status_filter(self, service, mock_repo):
        """Test listing workflows with status filter."""
        mock_repo.list_workflows.return_value = []
        
        service.list_workflows(status=WorkflowStatus.ACTIVE)
        
        mock_repo.list_workflows.assert_called_once_with(
            status=WorkflowStatus.ACTIVE, limit=100, offset=0
        )
