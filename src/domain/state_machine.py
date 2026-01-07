"""
State machine for workflow execution lifecycle.

Enforces valid state transitions and provides a clean API for managing
workflow execution states. This is a critical component for ensuring
workflow integrity.
"""

from typing import Dict, Set, Optional
from .enums import ExecutionStatus


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    
    def __init__(self, from_state: ExecutionStatus, to_state: ExecutionStatus):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition from {from_state.value} to {to_state.value}"
        )


class WorkflowStateMachine:
    """
    State machine for workflow execution status transitions.
    
    Valid transitions:
    - PENDING → RUNNING: Execution starts
    - RUNNING → COMPLETED: All steps succeed
    - RUNNING → FAILED: A step fails
    - FAILED → RETRYING: Retry is initiated
    - RETRYING → RUNNING: Retry execution starts
    - RETRYING → FAILED: Retry preparation fails
    - Any non-terminal → CANCELLED: Manual cancellation
    
    Terminal states: COMPLETED, FAILED (after max retries), CANCELLED
    """
    
    # Define valid transitions: from_state -> set of valid to_states
    TRANSITIONS: Dict[ExecutionStatus, Set[ExecutionStatus]] = {
        ExecutionStatus.PENDING: {
            ExecutionStatus.RUNNING,
            ExecutionStatus.CANCELLED,
        },
        ExecutionStatus.RUNNING: {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        },
        ExecutionStatus.FAILED: {
            ExecutionStatus.RETRYING,
            ExecutionStatus.CANCELLED,
        },
        ExecutionStatus.RETRYING: {
            ExecutionStatus.RUNNING,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        },
        ExecutionStatus.COMPLETED: set(),  # Terminal state
        ExecutionStatus.CANCELLED: set(),  # Terminal state
    }
    
    # States that indicate execution is finished
    TERMINAL_STATES: Set[ExecutionStatus] = {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    }
    
    # States that allow retry
    RETRYABLE_STATES: Set[ExecutionStatus] = {
        ExecutionStatus.FAILED,
    }
    
    @classmethod
    def can_transition(
        cls,
        from_state: ExecutionStatus,
        to_state: ExecutionStatus,
    ) -> bool:
        """Check if a transition is valid."""
        valid_transitions = cls.TRANSITIONS.get(from_state, set())
        return to_state in valid_transitions
    
    @classmethod
    def validate_transition(
        cls,
        from_state: ExecutionStatus,
        to_state: ExecutionStatus,
    ) -> None:
        """Validate a transition, raising an error if invalid."""
        if not cls.can_transition(from_state, to_state):
            raise InvalidTransitionError(from_state, to_state)
    
    @classmethod
    def transition(
        cls,
        from_state: ExecutionStatus,
        to_state: ExecutionStatus,
    ) -> ExecutionStatus:
        """
        Perform a state transition.
        
        Returns the new state if valid, raises InvalidTransitionError otherwise.
        """
        cls.validate_transition(from_state, to_state)
        return to_state
    
    @classmethod
    def is_terminal(cls, state: ExecutionStatus) -> bool:
        """Check if a state is terminal (no further transitions possible)."""
        return state in cls.TERMINAL_STATES
    
    @classmethod
    def can_retry(cls, state: ExecutionStatus) -> bool:
        """Check if an execution in this state can be retried."""
        return state in cls.RETRYABLE_STATES
    
    @classmethod
    def get_valid_transitions(cls, state: ExecutionStatus) -> Set[ExecutionStatus]:
        """Get all valid transitions from a given state."""
        return cls.TRANSITIONS.get(state, set()).copy()
    
    @classmethod
    def get_transition_path(
        cls,
        from_state: ExecutionStatus,
        to_state: ExecutionStatus,
    ) -> Optional[list]:
        """
        Find a valid path between two states using BFS.
        
        Returns the path as a list of states, or None if no path exists.
        Useful for debugging and understanding state flow.
        """
        if from_state == to_state:
            return [from_state]
        
        from collections import deque
        
        queue = deque([(from_state, [from_state])])
        visited = {from_state}
        
        while queue:
            current, path = queue.popleft()
            
            for next_state in cls.TRANSITIONS.get(current, set()):
                if next_state == to_state:
                    return path + [next_state]
                
                if next_state not in visited:
                    visited.add(next_state)
                    queue.append((next_state, path + [next_state]))
        
        return None
