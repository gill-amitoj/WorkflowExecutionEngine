"""
Unit tests for the state machine.
"""

import pytest

from src.domain.enums import ExecutionStatus
from src.domain.state_machine import (
    WorkflowStateMachine, InvalidTransitionError
)


class TestWorkflowStateMachine:
    """Tests for WorkflowStateMachine."""
    
    def test_valid_transition_pending_to_running(self):
        """Test PENDING → RUNNING transition."""
        result = WorkflowStateMachine.transition(
            ExecutionStatus.PENDING,
            ExecutionStatus.RUNNING,
        )
        assert result == ExecutionStatus.RUNNING
    
    def test_valid_transition_running_to_completed(self):
        """Test RUNNING → COMPLETED transition."""
        result = WorkflowStateMachine.transition(
            ExecutionStatus.RUNNING,
            ExecutionStatus.COMPLETED,
        )
        assert result == ExecutionStatus.COMPLETED
    
    def test_valid_transition_running_to_failed(self):
        """Test RUNNING → FAILED transition."""
        result = WorkflowStateMachine.transition(
            ExecutionStatus.RUNNING,
            ExecutionStatus.FAILED,
        )
        assert result == ExecutionStatus.FAILED
    
    def test_valid_transition_failed_to_retrying(self):
        """Test FAILED → RETRYING transition."""
        result = WorkflowStateMachine.transition(
            ExecutionStatus.FAILED,
            ExecutionStatus.RETRYING,
        )
        assert result == ExecutionStatus.RETRYING
    
    def test_valid_transition_retrying_to_running(self):
        """Test RETRYING → RUNNING transition."""
        result = WorkflowStateMachine.transition(
            ExecutionStatus.RETRYING,
            ExecutionStatus.RUNNING,
        )
        assert result == ExecutionStatus.RUNNING
    
    def test_valid_transition_to_cancelled(self):
        """Test that any non-terminal state can transition to CANCELLED."""
        for status in [
            ExecutionStatus.PENDING,
            ExecutionStatus.RUNNING,
            ExecutionStatus.FAILED,
            ExecutionStatus.RETRYING,
        ]:
            assert WorkflowStateMachine.can_transition(
                status, ExecutionStatus.CANCELLED
            )
    
    def test_invalid_transition_completed_to_running(self):
        """Test that COMPLETED is terminal and cannot transition."""
        with pytest.raises(InvalidTransitionError):
            WorkflowStateMachine.transition(
                ExecutionStatus.COMPLETED,
                ExecutionStatus.RUNNING,
            )
    
    def test_invalid_transition_pending_to_completed(self):
        """Test PENDING cannot skip to COMPLETED."""
        with pytest.raises(InvalidTransitionError):
            WorkflowStateMachine.transition(
                ExecutionStatus.PENDING,
                ExecutionStatus.COMPLETED,
            )
    
    def test_invalid_transition_pending_to_failed(self):
        """Test PENDING cannot skip to FAILED."""
        with pytest.raises(InvalidTransitionError):
            WorkflowStateMachine.transition(
                ExecutionStatus.PENDING,
                ExecutionStatus.FAILED,
            )
    
    def test_can_transition(self):
        """Test can_transition method."""
        assert WorkflowStateMachine.can_transition(
            ExecutionStatus.PENDING, ExecutionStatus.RUNNING
        )
        assert not WorkflowStateMachine.can_transition(
            ExecutionStatus.PENDING, ExecutionStatus.COMPLETED
        )
    
    def test_is_terminal(self):
        """Test is_terminal method."""
        assert WorkflowStateMachine.is_terminal(ExecutionStatus.COMPLETED)
        assert WorkflowStateMachine.is_terminal(ExecutionStatus.FAILED)
        assert WorkflowStateMachine.is_terminal(ExecutionStatus.CANCELLED)
        assert not WorkflowStateMachine.is_terminal(ExecutionStatus.PENDING)
        assert not WorkflowStateMachine.is_terminal(ExecutionStatus.RUNNING)
        assert not WorkflowStateMachine.is_terminal(ExecutionStatus.RETRYING)
    
    def test_can_retry(self):
        """Test can_retry method."""
        assert WorkflowStateMachine.can_retry(ExecutionStatus.FAILED)
        assert not WorkflowStateMachine.can_retry(ExecutionStatus.COMPLETED)
        assert not WorkflowStateMachine.can_retry(ExecutionStatus.RUNNING)
    
    def test_get_valid_transitions(self):
        """Test get_valid_transitions method."""
        pending_transitions = WorkflowStateMachine.get_valid_transitions(
            ExecutionStatus.PENDING
        )
        assert ExecutionStatus.RUNNING in pending_transitions
        assert ExecutionStatus.CANCELLED in pending_transitions
        assert ExecutionStatus.COMPLETED not in pending_transitions
    
    def test_get_transition_path_direct(self):
        """Test finding direct transition path."""
        path = WorkflowStateMachine.get_transition_path(
            ExecutionStatus.PENDING,
            ExecutionStatus.RUNNING,
        )
        assert path == [ExecutionStatus.PENDING, ExecutionStatus.RUNNING]
    
    def test_get_transition_path_multi_step(self):
        """Test finding multi-step transition path."""
        path = WorkflowStateMachine.get_transition_path(
            ExecutionStatus.PENDING,
            ExecutionStatus.COMPLETED,
        )
        # Should find: PENDING → RUNNING → COMPLETED
        assert path is not None
        assert path[0] == ExecutionStatus.PENDING
        assert path[-1] == ExecutionStatus.COMPLETED
        assert len(path) == 3
    
    def test_get_transition_path_no_path(self):
        """Test when no valid path exists."""
        path = WorkflowStateMachine.get_transition_path(
            ExecutionStatus.COMPLETED,
            ExecutionStatus.RUNNING,
        )
        assert path is None
    
    def test_get_transition_path_same_state(self):
        """Test path from state to itself."""
        path = WorkflowStateMachine.get_transition_path(
            ExecutionStatus.RUNNING,
            ExecutionStatus.RUNNING,
        )
        assert path == [ExecutionStatus.RUNNING]
    
    def test_invalid_transition_error_message(self):
        """Test error message contains state information."""
        try:
            WorkflowStateMachine.transition(
                ExecutionStatus.COMPLETED,
                ExecutionStatus.RUNNING,
            )
            pytest.fail("Should have raised InvalidTransitionError")
        except InvalidTransitionError as e:
            assert e.from_state == ExecutionStatus.COMPLETED
            assert e.to_state == ExecutionStatus.RUNNING
            assert "completed" in str(e).lower()
            assert "running" in str(e).lower()
