"""
Redis-based task queue implementation.

Provides reliable message queuing with visibility timeout,
dead letter queue support, and idempotent processing.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import redis

from src.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class QueueMessage:
    """
    Represents a message in the task queue.
    
    Contains metadata for tracking processing state and retries.
    """
    id: str
    execution_id: str
    task_type: str
    payload: Dict[str, Any]
    created_at: float
    attempt: int = 1
    visibility_timeout: int = 30
    
    def to_json(self) -> str:
        """Serialize message to JSON."""
        return json.dumps({
            "id": self.id,
            "execution_id": self.execution_id,
            "task_type": self.task_type,
            "payload": self.payload,
            "created_at": self.created_at,
            "attempt": self.attempt,
            "visibility_timeout": self.visibility_timeout,
        })
    
    @classmethod
    def from_json(cls, data: str) -> "QueueMessage":
        """Deserialize message from JSON."""
        obj = json.loads(data)
        return cls(
            id=obj["id"],
            execution_id=obj["execution_id"],
            task_type=obj["task_type"],
            payload=obj["payload"],
            created_at=obj["created_at"],
            attempt=obj.get("attempt", 1),
            visibility_timeout=obj.get("visibility_timeout", 30),
        )
    
    @classmethod
    def create(
        cls,
        execution_id: UUID,
        task_type: str = "execute_workflow",
        payload: Optional[Dict[str, Any]] = None,
        visibility_timeout: int = 30,
    ) -> "QueueMessage":
        """Factory method to create a new message."""
        return cls(
            id=str(uuid4()),
            execution_id=str(execution_id),
            task_type=task_type,
            payload=payload or {},
            created_at=time.time(),
            visibility_timeout=visibility_timeout,
        )


class TaskQueue:
    """
    Redis-based task queue with reliability features.
    
    Features:
    - Message persistence
    - Visibility timeout (messages return if not acknowledged)
    - Dead letter queue for failed messages
    - Idempotency checking
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        queue_name: Optional[str] = None,
    ):
        config = get_config()
        self.redis_url = redis_url or config.REDIS_URL
        self.queue_name = queue_name or config.QUEUE_NAME
        self.processing_queue = f"{self.queue_name}:processing"
        self.dlq_name = f"{self.queue_name}:dlq"
        self.idempotency_prefix = f"{self.queue_name}:idempotency"
        self.visibility_timeout = config.QUEUE_PROCESSING_TIMEOUT
        
        self._redis: Optional[redis.Redis] = None
    
    @property
    def redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                decode_responses=True,
            )
        return self._redis
    
    def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            self._redis.close()
            self._redis = None
    
    def enqueue(
        self,
        execution_id: UUID,
        task_type: str = "execute_workflow",
        payload: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        delay_seconds: int = 0,
    ) -> Optional[QueueMessage]:
        """
        Add a message to the queue.
        
        Args:
            execution_id: The execution ID to process
            task_type: Type of task
            payload: Additional payload data
            idempotency_key: Key to prevent duplicate processing
            delay_seconds: Delay before message becomes available
            
        Returns:
            The queued message, or None if duplicate
        """
        # Check idempotency
        if idempotency_key:
            idem_key = f"{self.idempotency_prefix}:{idempotency_key}"
            if not self.redis.setnx(idem_key, "1"):
                logger.info(f"Duplicate message rejected: {idempotency_key}")
                return None
            # Set TTL for idempotency key (24 hours)
            self.redis.expire(idem_key, 86400)
        
        message = QueueMessage.create(
            execution_id=execution_id,
            task_type=task_type,
            payload=payload,
            visibility_timeout=self.visibility_timeout,
        )
        
        if delay_seconds > 0:
            # Use sorted set for delayed messages
            score = time.time() + delay_seconds
            self.redis.zadd(f"{self.queue_name}:delayed", {message.to_json(): score})
            logger.info(f"Enqueued delayed message {message.id} for {delay_seconds}s")
        else:
            self.redis.lpush(self.queue_name, message.to_json())
            logger.info(f"Enqueued message {message.id}")
        
        return message
    
    def dequeue(self, timeout: int = 5) -> Optional[QueueMessage]:
        """
        Get a message from the queue.
        
        Uses BRPOPLPUSH for atomic move to processing queue.
        Returns None if no message available within timeout.
        """
        # First, move any ready delayed messages
        self._move_ready_delayed_messages()
        
        # Try to get a message
        result = self.redis.brpoplpush(
            self.queue_name,
            self.processing_queue,
            timeout=timeout,
        )
        
        if not result:
            return None
        
        message = QueueMessage.from_json(result)
        
        # Set visibility timeout
        self.redis.setex(
            f"{self.processing_queue}:{message.id}",
            message.visibility_timeout,
            result,
        )
        
        logger.debug(f"Dequeued message {message.id}")
        return message
    
    def acknowledge(self, message: QueueMessage) -> bool:
        """
        Acknowledge successful processing of a message.
        
        Removes message from processing queue.
        """
        # Remove from processing queue
        self.redis.lrem(self.processing_queue, 1, message.to_json())
        
        # Delete visibility timeout key
        self.redis.delete(f"{self.processing_queue}:{message.id}")
        
        logger.debug(f"Acknowledged message {message.id}")
        return True
    
    def reject(
        self,
        message: QueueMessage,
        requeue: bool = True,
        send_to_dlq: bool = False,
    ) -> bool:
        """
        Reject a message - either requeue or send to DLQ.
        
        Args:
            message: The message to reject
            requeue: If True, put back in main queue for retry
            send_to_dlq: If True, send to dead letter queue
        """
        # Remove from processing queue
        self.redis.lrem(self.processing_queue, 1, message.to_json())
        self.redis.delete(f"{self.processing_queue}:{message.id}")
        
        if send_to_dlq:
            # Send to dead letter queue
            message.payload["dlq_reason"] = "rejected"
            message.payload["dlq_timestamp"] = time.time()
            self.redis.lpush(self.dlq_name, message.to_json())
            logger.warning(f"Message {message.id} sent to DLQ")
        elif requeue:
            # Increment attempt and requeue
            message.attempt += 1
            self.redis.lpush(self.queue_name, message.to_json())
            logger.info(f"Message {message.id} requeued (attempt {message.attempt})")
        
        return True
    
    def get_queue_length(self) -> int:
        """Get the number of messages in the main queue."""
        return self.redis.llen(self.queue_name)
    
    def get_processing_length(self) -> int:
        """Get the number of messages being processed."""
        return self.redis.llen(self.processing_queue)
    
    def get_dlq_length(self) -> int:
        """Get the number of messages in the dead letter queue."""
        return self.redis.llen(self.dlq_name)
    
    def recover_stale_messages(self) -> int:
        """
        Recover messages that have exceeded visibility timeout.
        
        These are messages where processing started but never completed.
        Returns the number of recovered messages.
        """
        recovered = 0
        messages = self.redis.lrange(self.processing_queue, 0, -1)
        
        for msg_json in messages:
            message = QueueMessage.from_json(msg_json)
            timeout_key = f"{self.processing_queue}:{message.id}"
            
            # If timeout key doesn't exist, message is stale
            if not self.redis.exists(timeout_key):
                self.redis.lrem(self.processing_queue, 1, msg_json)
                
                # Requeue with incremented attempt
                message.attempt += 1
                if message.attempt <= 3:  # Max 3 attempts
                    self.redis.lpush(self.queue_name, message.to_json())
                    logger.warning(f"Recovered stale message {message.id}")
                else:
                    # Send to DLQ
                    message.payload["dlq_reason"] = "max_attempts_exceeded"
                    self.redis.lpush(self.dlq_name, message.to_json())
                    logger.warning(f"Stale message {message.id} sent to DLQ")
                
                recovered += 1
        
        return recovered
    
    def _move_ready_delayed_messages(self) -> int:
        """Move delayed messages that are ready to the main queue."""
        now = time.time()
        delayed_queue = f"{self.queue_name}:delayed"
        
        # Get messages with score <= now
        messages = self.redis.zrangebyscore(delayed_queue, 0, now)
        
        if not messages:
            return 0
        
        pipe = self.redis.pipeline()
        for msg_json in messages:
            pipe.lpush(self.queue_name, msg_json)
            pipe.zrem(delayed_queue, msg_json)
        pipe.execute()
        
        return len(messages)
    
    def clear_all(self) -> None:
        """Clear all queues. Use with caution - mainly for testing."""
        self.redis.delete(self.queue_name)
        self.redis.delete(self.processing_queue)
        self.redis.delete(self.dlq_name)
        self.redis.delete(f"{self.queue_name}:delayed")
        logger.warning("All queues cleared")
    
    def health_check(self) -> bool:
        """Check if Redis is accessible."""
        try:
            return self.redis.ping()
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
