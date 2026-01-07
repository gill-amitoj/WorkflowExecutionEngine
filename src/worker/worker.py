"""
Background worker for processing workflow executions.

Polls the task queue and executes workflows using the orchestrator.
"""

import logging
import signal
import threading
import time
from typing import Optional
from uuid import UUID

from src.config import get_config
from src.persistence import Database, WorkflowRepository, ExecutionRepository, LogRepository
from src.services import WorkflowOrchestrator
from src.services.task_handlers import create_default_registry
from .queue import TaskQueue, QueueMessage

logger = logging.getLogger(__name__)


class Worker:
    """
    Background worker for processing workflow tasks.
    
    Features:
    - Graceful shutdown on SIGTERM/SIGINT
    - Configurable concurrency (via multiple worker instances)
    - Automatic retry handling
    - Health check endpoint support
    """
    
    def __init__(
        self,
        queue: Optional[TaskQueue] = None,
        db: Optional[Database] = None,
    ):
        self.config = get_config()
        self.queue = queue or TaskQueue()
        self.db = db or Database()
        self.db.initialize()
        
        # Create repositories
        self.workflow_repo = WorkflowRepository(self.db)
        self.execution_repo = ExecutionRepository(self.db)
        self.log_repo = LogRepository(self.db)
        
        # Create orchestrator with task registry
        self.task_registry = create_default_registry()
        self.orchestrator = WorkflowOrchestrator(
            workflow_repo=self.workflow_repo,
            execution_repo=self.execution_repo,
            log_repo=self.log_repo,
            task_registry=self.task_registry,
        )
        
        # Worker state
        self._running = False
        self._shutdown_event = threading.Event()
        self._current_message: Optional[QueueMessage] = None
    
    def start(self) -> None:
        """Start the worker loop."""
        self._running = True
        self._setup_signal_handlers()
        
        logger.info("Worker started, waiting for tasks...")
        
        # Start recovery thread for stale messages
        recovery_thread = threading.Thread(target=self._recovery_loop, daemon=True)
        recovery_thread.start()
        
        # Main processing loop
        while self._running:
            try:
                self._process_one()
            except Exception as e:
                logger.exception(f"Error in worker loop: {e}")
                time.sleep(1)  # Brief pause on error
        
        logger.info("Worker stopped")
    
    def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("Stopping worker...")
        self._running = False
        self._shutdown_event.set()
    
    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        def handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            self.stop()
        
        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGINT, handler)
    
    def _process_one(self) -> bool:
        """
        Process a single message from the queue.
        
        Returns True if a message was processed, False otherwise.
        """
        message = self.queue.dequeue(timeout=5)
        
        if not message:
            return False
        
        self._current_message = message
        
        try:
            logger.info(
                f"Processing message {message.id} "
                f"(execution: {message.execution_id}, attempt: {message.attempt})"
            )
            
            # Execute the workflow
            execution_id = UUID(message.execution_id)
            result = self.orchestrator.execute(execution_id)
            
            # Success - acknowledge the message
            self.queue.acknowledge(message)
            logger.info(f"Message {message.id} completed: {result.get('status')}")
            
            return True
            
        except Exception as e:
            logger.exception(f"Failed to process message {message.id}: {e}")
            
            # Determine whether to retry or send to DLQ
            max_attempts = self.config.MAX_RETRIES
            send_to_dlq = message.attempt >= max_attempts
            
            self.queue.reject(
                message,
                requeue=not send_to_dlq,
                send_to_dlq=send_to_dlq,
            )
            
            return False
        
        finally:
            self._current_message = None
    
    def _recovery_loop(self) -> None:
        """
        Background loop to recover stale messages.
        
        Runs periodically to find messages that were being processed
        but never acknowledged (e.g., due to worker crash).
        """
        recovery_interval = 60  # seconds
        
        while not self._shutdown_event.wait(recovery_interval):
            try:
                recovered = self.queue.recover_stale_messages()
                if recovered > 0:
                    logger.info(f"Recovered {recovered} stale messages")
            except Exception as e:
                logger.error(f"Error in recovery loop: {e}")
    
    @property
    def is_healthy(self) -> bool:
        """Check if the worker is healthy."""
        try:
            db_healthy = self.db.health_check()
            queue_healthy = self.queue.health_check()
            return db_healthy and queue_healthy
        except Exception:
            return False
    
    def get_stats(self) -> dict:
        """Get worker statistics."""
        return {
            "running": self._running,
            "queue_length": self.queue.get_queue_length(),
            "processing_length": self.queue.get_processing_length(),
            "dlq_length": self.queue.get_dlq_length(),
            "current_message": self._current_message.id if self._current_message else None,
        }


def run_worker() -> None:
    """Entry point for running the worker."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    worker = Worker()
    worker.start()


if __name__ == "__main__":
    run_worker()
