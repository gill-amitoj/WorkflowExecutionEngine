"""
Unit tests for domain entities.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from src.domain.entities import (
    Workflow, WorkflowStep, WorkflowExecution, StepExecution, ExecutionLog
)
from src.domain.enums import (
    WorkflowStatus, ExecutionStatus, StepStatus, LogLevel
)


class TestWorkflow:
    """Tests for Workflow entity."""
    
    def test_create_workflow(self):
        """Test workflow factory method."""
        workflow = Workflow.create(
            name="test-workflow",
            description="Test description",
            metadata={"owner": "test"},
        )
        
        assert workflow.id is not None
        assert workflow.name == "test-workflow"
        assert workflow.description == "Test description"
        assert workflow.status == WorkflowStatus.DRAFT
        assert workflow.version == 1
        assert workflow.metadata == {"owner": "test"}
        assert workflow.steps == []
    
    def test_add_step(self):
        """Test adding steps to workflow."""
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
            step_order=1,
        )
        
        # Add out of order
        workflow.add_step(step2)
        workflow.add_step(step1)
        
        # Should be sorted by step_order
        assert len(workflow.steps) == 2
        assert workflow.steps[0].name == "step1"
        assert workflow.steps[1].name == "step2"
    
    def test_activate_workflow_without_steps(self):
        """Test that workflow cannot be activated without steps."""
        workflow = Workflow.create(name="test")
        
        with pytest.raises(ValueError, match="without steps"):
            workflow.activate()
    
    def test_activate_workflow_with_steps(self):
        """Test successful workflow activation."""
        workflow = Workflow.create(name="test")
        step = WorkflowStep.create(
            workflow_id=workflow.id,
            name="step1",
            task_type="log",
            step_order=0,
        )
        workflow.add_step(step)
        
        workflow.activate()
        
        assert workflow.status == WorkflowStatus.ACTIVE
    
    def test_activate_non_draft_workflow(self):
        """Test that only DRAFT workflows can be activated."""
        workflow = Workflow.create(name="test")
        step = WorkflowStep.create(
            workflow_id=workflow.id,
            name="step1",
            task_type="log",
            step_order=0,
        )
        workflow.add_step(step)
        workflow.activate()
        
        with pytest.raises(ValueError, match="Cannot activate"):
            workflow.activate()
    
    def test_deprecate_workflow(self):
        """Test workflow deprecation."""
        workflow = Workflow.create(name="test")
        step = WorkflowStep.create(
            workflow_id=workflow.id,
            name="step1",
            task_type="log",
            step_order=0,
        )
        workflow.add_step(step)
        workflow.activate()
        
        workflow.deprecate()
        
        assert workflow.status == WorkflowStatus.DEPRECATED
    
    def test_archive_workflow(self):
        """Test workflow archiving."""
        workflow = Workflow.create(name="test")
        
        workflow.archive()
        
        assert workflow.status == WorkflowStatus.ARCHIVED


class TestWorkflowStep:
    """Tests for WorkflowStep entity."""
    
    def test_create_step(self):
        """Test step factory method."""
        workflow_id = uuid4()
        step = WorkflowStep.create(
            workflow_id=workflow_id,
            name="test-step",
            task_type="http_request",
            step_order=0,
            config={"url": "http://example.com"},
            timeout_seconds=120,
            max_retries=5,
        )
        
        assert step.id is not None
        assert step.workflow_id == workflow_id
        assert step.name == "test-step"
        assert step.task_type == "http_request"
        assert step.step_order == 0
        assert step.config == {"url": "http://example.com"}
        assert step.timeout_seconds == 120
        assert step.max_retries == 5


class TestWorkflowExecution:
    """Tests for WorkflowExecution entity."""
    
    def test_create_execution(self):
        """Test execution factory method."""
        workflow_id = uuid4()
        execution = WorkflowExecution.create(
            workflow_id=workflow_id,
            idempotency_key="test-key-123",
            input_data={"key": "value"},
            max_retries=5,
        )
        
        assert execution.id is not None
        assert execution.workflow_id == workflow_id
        assert execution.idempotency_key == "test-key-123"
        assert execution.status == ExecutionStatus.PENDING
        assert execution.input_data == {"key": "value"}
        assert execution.max_retries == 5
        assert execution.retry_count == 0
    
    def test_is_terminal_property(self):
        """Test is_terminal property for different states."""
        execution = WorkflowExecution.create(
            workflow_id=uuid4(),
            idempotency_key="test",
        )
        
        # PENDING is not terminal
        assert not execution.is_terminal
        
        # COMPLETED is terminal
        execution.status = ExecutionStatus.COMPLETED
        assert execution.is_terminal
        
        # FAILED is terminal
        execution.status = ExecutionStatus.FAILED
        assert execution.is_terminal
        
        # CANCELLED is terminal
        execution.status = ExecutionStatus.CANCELLED
        assert execution.is_terminal
        
        # RUNNING is not terminal
        execution.status = ExecutionStatus.RUNNING
        assert not execution.is_terminal
    
    def test_can_retry_property(self):
        """Test can_retry property."""
        execution = WorkflowExecution.create(
            workflow_id=uuid4(),
            idempotency_key="test",
            max_retries=3,
        )
        
        # PENDING cannot retry
        assert not execution.can_retry
        
        # FAILED with retries left can retry
        execution.status = ExecutionStatus.FAILED
        execution.retry_count = 0
        assert execution.can_retry
        
        # FAILED at max retries cannot retry
        execution.retry_count = 3
        assert not execution.can_retry


class TestStepExecution:
    """Tests for StepExecution entity."""
    
    def test_create_step_execution(self):
        """Test step execution factory method."""
        execution_id = uuid4()
        step_id = uuid4()
        
        step_exec = StepExecution.create(
            execution_id=execution_id,
            step_id=step_id,
            step_order=0,
            input_data={"input": "data"},
        )
        
        assert step_exec.id is not None
        assert step_exec.execution_id == execution_id
        assert step_exec.step_id == step_id
        assert step_exec.status == StepStatus.PENDING
        assert step_exec.input_data == {"input": "data"}
    
    def test_start_step(self):
        """Test starting a step execution."""
        step_exec = StepExecution.create(
            execution_id=uuid4(),
            step_id=uuid4(),
            step_order=0,
        )
        
        step_exec.start()
        
        assert step_exec.status == StepStatus.RUNNING
        assert step_exec.started_at is not None
    
    def test_complete_step(self):
        """Test completing a step execution."""
        step_exec = StepExecution.create(
            execution_id=uuid4(),
            step_id=uuid4(),
            step_order=0,
        )
        
        step_exec.start()
        step_exec.complete(output_data={"result": "success"})
        
        assert step_exec.status == StepStatus.COMPLETED
        assert step_exec.output_data == {"result": "success"}
        assert step_exec.completed_at is not None
    
    def test_fail_step(self):
        """Test failing a step execution."""
        step_exec = StepExecution.create(
            execution_id=uuid4(),
            step_id=uuid4(),
            step_order=0,
        )
        
        step_exec.start()
        step_exec.fail("Something went wrong", {"traceback": "..."})
        
        assert step_exec.status == StepStatus.FAILED
        assert step_exec.error_message == "Something went wrong"
        assert step_exec.error_details == {"traceback": "..."}


class TestExecutionLog:
    """Tests for ExecutionLog entity."""
    
    def test_create_log(self):
        """Test log factory method."""
        execution_id = uuid4()
        
        log = ExecutionLog.create(
            execution_id=execution_id,
            level=LogLevel.INFO,
            message="Test message",
            details={"key": "value"},
        )
        
        assert log.id is not None
        assert log.execution_id == execution_id
        assert log.level == LogLevel.INFO
        assert log.message == "Test message"
        assert log.details == {"key": "value"}
    
    def test_info_helper(self):
        """Test info helper method."""
        execution_id = uuid4()
        
        log = ExecutionLog.info(
            execution_id,
            "Info message",
            extra_key="extra_value",
        )
        
        assert log.level == LogLevel.INFO
        assert log.message == "Info message"
        assert log.details["extra_key"] == "extra_value"
    
    def test_error_helper(self):
        """Test error helper method."""
        execution_id = uuid4()
        step_exec_id = uuid4()
        
        log = ExecutionLog.error(
            execution_id,
            "Error message",
            step_execution_id=step_exec_id,
            error_code="ERR001",
        )
        
        assert log.level == LogLevel.ERROR
        assert log.message == "Error message"
        assert log.step_execution_id == step_exec_id
        assert log.details["error_code"] == "ERR001"
