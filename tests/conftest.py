"""
Test configuration and fixtures.

Provides common fixtures for unit and integration tests.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

# Set test environment before importing app modules
os.environ["FLASK_ENV"] = "testing"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/workflow_engine_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"


@pytest.fixture
def mock_db():
    """Create a mock database for unit tests."""
    db = MagicMock()
    db.health_check.return_value = True
    return db


@pytest.fixture
def mock_redis():
    """Create a mock Redis client for unit tests."""
    import fakeredis
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def sample_workflow_data():
    """Sample workflow data for tests."""
    return {
        "name": "test-workflow",
        "description": "A test workflow",
        "metadata": {"owner": "test-user"},
    }


@pytest.fixture
def sample_step_data():
    """Sample step data for tests."""
    return {
        "name": "test-step",
        "task_type": "log",
        "step_order": 0,
        "config": {"message": "Hello, World!"},
        "timeout_seconds": 60,
        "max_retries": 3,
    }


@pytest.fixture
def sample_execution_data():
    """Sample execution data for tests."""
    return {
        "workflow_id": str(uuid4()),
        "idempotency_key": f"test-{uuid4()}",
        "input_data": {"key": "value"},
        "max_retries": 3,
    }


@pytest.fixture
def workflow_id():
    """Generate a test workflow ID."""
    return uuid4()


@pytest.fixture
def execution_id():
    """Generate a test execution ID."""
    return uuid4()


# ============================================
# Integration Test Fixtures
# ============================================

@pytest.fixture(scope="session")
def test_database():
    """
    Create a test database connection.
    
    Scope is session to reuse across tests.
    """
    from src.persistence.database import Database
    
    db = Database(
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/workflow_engine_test"
        )
    )
    
    try:
        db.initialize()
        yield db
    finally:
        db.close()


@pytest.fixture
def clean_database(test_database):
    """
    Clean database tables before each test.
    
    Use this fixture for integration tests that need a clean state.
    """
    # Clear tables in reverse dependency order
    with test_database.get_cursor() as cur:
        cur.execute("TRUNCATE execution_logs CASCADE")
        cur.execute("TRUNCATE step_executions CASCADE")
        cur.execute("TRUNCATE workflow_executions CASCADE")
        cur.execute("TRUNCATE workflow_steps CASCADE")
        cur.execute("TRUNCATE workflows CASCADE")
    
    yield test_database


@pytest.fixture
def app(mock_db):
    """Create Flask test application."""
    from src.api.app import create_app
    from src.config import TestConfig
    
    with patch('src.api.app.get_database', return_value=mock_db):
        app = create_app(TestConfig())
        app.config["TESTING"] = True
        yield app


@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()
