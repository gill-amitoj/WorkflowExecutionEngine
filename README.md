# Workflow Orchestration Engine

A production-grade backend system for executing multi-step workflows with retries, failure recovery, and audit logging. Built with Python, Flask, PostgreSQL, and Redis.

## 🎯 Project Overview

This workflow orchestration engine demonstrates:
- **System Design Thinking**: Clean architecture with separation of concerns
- **Backend Engineering Depth**: State machine, retry logic, idempotency
- **Failure Handling**: Graceful recovery, resumable executions
- **Clean Architecture**: Domain-driven design with clear boundaries

## 📐 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer (Flask)                        │
│  /api/v1/workflows, /api/v1/executions, /health                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Service Layer                               │
│  WorkflowService │ ExecutionService │ WorkflowOrchestrator      │
└─────────────────────────────────────────────────────────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
┌───────────────────┐ ┌─────────────────┐ ┌────────────────────┐
│   Domain Layer    │ │ Persistence     │ │   Worker Layer     │
│ Entities, Enums,  │ │ Repositories,   │ │ TaskQueue, Worker  │
│ State Machine     │ │ Database        │ │ Task Handlers      │
└───────────────────┘ └─────────────────┘ └────────────────────┘
                                │                   │
                                ▼                   ▼
                    ┌───────────────────┐ ┌────────────────────┐
                    │    PostgreSQL     │ │       Redis        │
                    │   (Persistence)   │ │   (Task Queue)     │
                    └───────────────────┘ └────────────────────┘
```

### Layer Responsibilities

| Layer | Responsibility |
|-------|---------------|
| **API** | HTTP routing, request validation, response formatting |
| **Service** | Business logic, orchestration, state management |
| **Domain** | Entities, enums, state machine rules |
| **Persistence** | Data access, SQL queries, transaction management |
| **Worker** | Background processing, retry logic, queue management |

## 🔄 State Machine

Workflow executions follow a strict state machine:

```
                    ┌──────────────┐
                    │   PENDING    │
                    └──────┬───────┘
                           │ start
                           ▼
                    ┌──────────────┐
            ┌───────│   RUNNING    │───────┐
            │       └──────────────┘       │
            │ success              failure │
            ▼                              ▼
     ┌──────────────┐              ┌──────────────┐
     │  COMPLETED   │              │    FAILED    │
     └──────────────┘              └──────┬───────┘
                                          │ retry (if attempts < max)
                                          ▼
                                   ┌──────────────┐
                                   │   RETRYING   │
                                   └──────┬───────┘
                                          │
                                          └──────► RUNNING
                    
     Any non-terminal state ─────► CANCELLED
```

### State Descriptions

| State | Description |
|-------|-------------|
| `PENDING` | Execution queued, waiting to start |
| `RUNNING` | Execution in progress |
| `COMPLETED` | All steps succeeded |
| `FAILED` | Execution failed (may be retried) |
| `RETRYING` | Scheduled for retry |
| `CANCELLED` | Manually cancelled |

## 📊 Data Model

### Entity Relationship Diagram

```
┌─────────────────┐       ┌─────────────────────┐
│    workflows    │       │   workflow_steps    │
├─────────────────┤       ├─────────────────────┤
│ id (PK)         │───┐   │ id (PK)             │
│ name            │   │   │ workflow_id (FK)    │───┐
│ description     │   └──►│ name                │   │
│ status          │       │ task_type           │   │
│ version         │       │ step_order          │   │
│ metadata        │       │ config              │   │
│ created_at      │       │ timeout_seconds     │   │
│ updated_at      │       │ max_retries         │   │
└─────────────────┘       └─────────────────────┘   │
                                                     │
┌─────────────────────┐   ┌─────────────────────┐   │
│ workflow_executions │   │  step_executions    │   │
├─────────────────────┤   ├─────────────────────┤   │
│ id (PK)             │──►│ id (PK)             │   │
│ workflow_id (FK)    │   │ execution_id (FK)   │   │
│ idempotency_key     │   │ step_id (FK)        │◄──┘
│ status              │   │ step_order          │
│ current_step_order  │   │ status              │
│ retry_count         │   │ attempt_number      │
│ max_retries         │   │ input_data          │
│ input_data          │   │ output_data         │
│ output_data         │   │ error_message       │
│ error_message       │   │ error_details       │
│ scheduled_at        │   │ started_at          │
│ started_at          │   │ completed_at        │
│ completed_at        │   └─────────────────────┘
└─────────────────────┘
            │
            │   ┌─────────────────────┐
            │   │   execution_logs    │
            │   ├─────────────────────┤
            └──►│ id (PK)             │
                │ execution_id (FK)   │
                │ step_execution_id   │
                │ level               │
                │ message             │
                │ details             │
                │ timestamp           │
                └─────────────────────┘
```

### Key Design Decisions

1. **Idempotency Keys**: Prevent duplicate executions via unique `(workflow_id, idempotency_key)` constraint
2. **Resumable Executions**: `current_step_order` tracks progress for restart from failure point
3. **Audit Trail**: `execution_logs` captures every significant event
4. **Flexible Configuration**: JSONB `config` allows step-specific settings

## 🚀 API Reference

### Workflow Endpoints

#### Create Workflow
```http
POST /api/v1/workflows
Content-Type: application/json

{
  "name": "order-processing",
  "description": "Process new orders",
  "metadata": {"owner": "order-team"}
}

Response: 201 Created
{
  "id": "uuid",
  "name": "order-processing",
  "status": "draft",
  ...
}
```

#### Add Step to Workflow
```http
POST /api/v1/workflows/{workflow_id}/steps
Content-Type: application/json

{
  "name": "validate-order",
  "task_type": "http_request",
  "step_order": 0,
  "config": {
    "url": "https://api.internal/validate",
    "method": "POST"
  },
  "timeout_seconds": 60,
  "max_retries": 3
}

Response: 201 Created
```

#### Activate Workflow
```http
POST /api/v1/workflows/{workflow_id}/activate

Response: 200 OK
```

#### List Workflows
```http
GET /api/v1/workflows?status=active&limit=50&offset=0

Response: 200 OK
{
  "workflows": [...],
  "count": 10,
  "limit": 50,
  "offset": 0
}
```

### Execution Endpoints

#### Trigger Execution
```http
POST /api/v1/executions
Content-Type: application/json

{
  "workflow_id": "uuid",
  "idempotency_key": "order-12345",
  "input_data": {"order_id": "12345"},
  "max_retries": 3
}

Response: 201 Created (new) or 200 OK (existing)
```

#### Get Execution Status
```http
GET /api/v1/executions/{execution_id}

Response: 200 OK
{
  "id": "uuid",
  "status": "running",
  "current_step_order": 2,
  "retry_count": 0,
  ...
}
```

#### Retry Failed Execution
```http
POST /api/v1/executions/{execution_id}/retry

Response: 200 OK
```

#### Cancel Execution
```http
POST /api/v1/executions/{execution_id}/cancel

Response: 200 OK
```

#### Get Execution Logs
```http
GET /api/v1/executions/{execution_id}/logs?level=error

Response: 200 OK
{
  "logs": [
    {
      "level": "error",
      "message": "Step 'validate' failed",
      "details": {...},
      "timestamp": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### Health Check
```http
GET /health

Response: 200 OK (healthy) or 503 (unhealthy)
{
  "status": "healthy",
  "database": "healthy",
  "redis": "healthy"
}
```

## 🔧 Task Handlers

Built-in task types:

| Type | Description | Example Config |
|------|-------------|----------------|
| `http_request` | Make HTTP requests | `{"url": "...", "method": "POST", "body": {...}}` |
| `data_transform` | Transform data | `{"transforms": [{"type": "rename", "from": "a", "to": "b"}]}` |
| `delay` | Wait/sleep | `{"seconds": 5}` |
| `conditional` | Branch logic | `{"condition": {"field": "x", "operator": "eq", "value": "y"}}` |
| `log` | Log messages | `{"message": "Processing {order_id}", "level": "info"}` |

### Custom Task Handlers

```python
from src.services.task_handlers import TaskHandler, TaskHandlerRegistry

class MyCustomHandler(TaskHandler):
    @property
    def task_type(self) -> str:
        return "my_custom_task"
    
    def execute(self, step_config, input_data, timeout=300):
        # Your logic here
        return {"result": "success"}

# Register
registry = TaskHandlerRegistry()
registry.register(MyCustomHandler())
```

## 🏃 Running the Project

### Prerequisites
- Docker and Docker Compose
- Python 3.11+ (for local development)

### Quick Start with Docker

```bash
# Clone and start
git clone <repo>
cd workflow-orchestration-engine

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check health
curl http://localhost:5000/health
```

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env

# Start PostgreSQL and Redis (via Docker)
docker-compose up -d postgres redis

# Run migrations
psql $DATABASE_URL -f migrations/001_initial_schema.sql

# Start API server
flask run

# Start worker (in another terminal)
python -m src.worker.worker
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run only unit tests
pytest tests/unit -v

# Run specific test file
pytest tests/unit/test_state_machine.py -v
```

## 📁 Project Structure

```
workflow-orchestration-engine/
├── src/
│   ├── api/                    # API Layer
│   │   ├── app.py              # Flask app factory
│   │   └── routes.py           # API endpoints
│   ├── config/                 # Configuration
│   │   └── settings.py         # Environment config
│   ├── domain/                 # Domain Layer
│   │   ├── entities.py         # Domain objects
│   │   ├── enums.py            # Status enums
│   │   └── state_machine.py    # State transitions
│   ├── persistence/            # Persistence Layer
│   │   ├── database.py         # DB connection
│   │   └── repositories.py     # Data access
│   ├── services/               # Service Layer
│   │   ├── workflow_service.py # Workflow management
│   │   ├── execution_service.py# Execution management
│   │   ├── orchestrator.py     # Execution engine
│   │   └── task_handlers.py    # Task implementations
│   └── worker/                 # Worker Layer
│       ├── queue.py            # Redis queue
│       └── worker.py           # Background worker
├── tests/
│   ├── unit/                   # Unit tests
│   └── integration/            # Integration tests
├── migrations/                 # SQL migrations
├── Dockerfile                  # API container
├── Dockerfile.worker           # Worker container
├── docker-compose.yml          # Full stack
└── requirements.txt            # Dependencies
```

## ⚖️ Design Tradeoffs

### 1. Synchronous vs Asynchronous Execution
**Choice**: Asynchronous with Redis queue

**Pros**:
- Decouples API from long-running tasks
- Enables horizontal scaling of workers
- Better failure isolation

**Cons**:
- Added complexity
- Requires Redis infrastructure
- Harder to debug

### 2. PostgreSQL vs NoSQL
**Choice**: PostgreSQL with JSONB

**Pros**:
- ACID transactions for state consistency
- Flexible JSONB for config/metadata
- Strong query capabilities

**Cons**:
- Less horizontal scalability
- Schema migrations needed

### 3. State Machine Implementation
**Choice**: In-memory state machine with DB persistence

**Pros**:
- Clear state transition rules
- Easy to test and verify
- Self-documenting behavior

**Cons**:
- Race conditions possible without locking
- State logic spread across layers

### 4. Retry Strategy
**Choice**: Exponential backoff with max retries

**Pros**:
- Prevents thundering herd
- Gives transient failures time to recover
- Configurable per-step

**Cons**:
- Can delay recovery for known-fixable errors
- Memory overhead for waiting tasks

### 5. Idempotency Implementation
**Choice**: Database constraint + Redis deduplication

**Pros**:
- Prevents duplicate executions
- Safe for concurrent triggers
- Client-controlled keys

**Cons**:
- Requires client to manage keys
- Storage overhead for keys

## 🔒 Production Considerations

For production deployment, consider:

1. **Security**
   - Change `SECRET_KEY` to a strong random value
   - Use SSL/TLS for all connections
   - Implement authentication (JWT, OAuth)
   - Rate limiting

2. **Monitoring**
   - Add Prometheus metrics
   - Structured logging (JSON)
   - Distributed tracing (OpenTelemetry)
   - Alerting on failure rates

3. **Scalability**
   - Multiple worker instances
   - Connection pooling tuning
   - Redis cluster for queue
   - Read replicas for queries

4. **Reliability**
   - Database backups
   - Redis persistence (AOF)
   - Health check endpoints
   - Circuit breakers for external calls

## 📜 License

MIT License

---

If you have any questions or feedback, feel free to reach out!
