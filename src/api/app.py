"""
Flask application factory.

Creates and configures the Flask application with all necessary
extensions and error handlers.
"""

import logging
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from src.config import get_config
from src.persistence import Database, get_database

logger = logging.getLogger(__name__)


def create_app(config=None) -> Flask:
    """
    Application factory for creating Flask app.
    
    Args:
        config: Optional configuration object
        
    Returns:
        Configured Flask application
    """
    app = Flask(__name__)
    
    # Enable CORS for all routes
    CORS(app)
    
    # Load configuration
    app_config = config or get_config()
    app.config["SECRET_KEY"] = app_config.SECRET_KEY
    app.config["DEBUG"] = app_config.FLASK_DEBUG
    
    # Store config for access in routes
    app.config["APP_CONFIG"] = app_config
    
    # Initialize database
    db = get_database()
    app.config["DATABASE"] = db
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register routes
    from .routes import register_routes
    register_routes(app)
    
    # Health check endpoint
    @app.route("/health")
    def health_check():
        """Health check endpoint."""
        db = app.config["DATABASE"]
        db_healthy = db.health_check()
        
        # Try Redis health check if queue is available
        redis_healthy = True
        try:
            from src.worker import TaskQueue
            queue = TaskQueue()
            redis_healthy = queue.health_check()
        except Exception:
            redis_healthy = False
        
        status = "healthy" if (db_healthy and redis_healthy) else "unhealthy"
        status_code = 200 if status == "healthy" else 503
        
        return jsonify({
            "status": status,
            "database": "healthy" if db_healthy else "unhealthy",
            "redis": "healthy" if redis_healthy else "unhealthy",
        }), status_code
    
    logger.info("Flask application created")
    return app


def register_error_handlers(app: Flask) -> None:
    """Register error handlers for the application."""
    
    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        """Handle HTTP exceptions."""
        response = {
            "error": {
                "code": e.code,
                "name": e.name,
                "message": e.description,
            }
        }
        return jsonify(response), e.code
    
    @app.errorhandler(ValueError)
    def handle_value_error(e: ValueError):
        """Handle validation errors."""
        return jsonify({
            "error": {
                "code": 400,
                "name": "Bad Request",
                "message": str(e),
            }
        }), 400
    
    @app.errorhandler(Exception)
    def handle_generic_exception(e: Exception):
        """Handle unexpected errors."""
        logger.exception(f"Unhandled exception: {e}")
        return jsonify({
            "error": {
                "code": 500,
                "name": "Internal Server Error",
                "message": "An unexpected error occurred",
            }
        }), 500
