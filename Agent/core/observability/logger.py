"""
Structured Logger - JSON-formatted logging with trace IDs.
"""
import logging
import json
import sys
from datetime import datetime
from typing import Optional, Dict, Any
import uuid

class StructuredLogger:
    """Structured JSON logger with trace ID support."""
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Add structured handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(handler)
        
        self.trace_id: Optional[str] = None
    
    def set_trace_id(self, trace_id: Optional[str] = None):
        """Set trace ID for request correlation."""
        self.trace_id = trace_id or str(uuid.uuid4())
        return self.trace_id
    
    def _log(self, level: str, message: str, **kwargs):
        """Internal log method with structured data."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
            "trace_id": self.trace_id,
            **kwargs
        }
        
        if level == "DEBUG":
            self.logger.debug(json.dumps(log_data))
        elif level == "INFO":
            self.logger.info(json.dumps(log_data))
        elif level == "WARNING":
            self.logger.warning(json.dumps(log_data))
        elif level == "ERROR":
            self.logger.error(json.dumps(log_data))
        elif level == "CRITICAL":
            self.logger.critical(json.dumps(log_data))
    
    def debug(self, message: str, **kwargs):
        self._log("DEBUG", message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log("INFO", message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log("WARNING", message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log("ERROR", message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log("CRITICAL", message, **kwargs)

class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logs."""
    
    def format(self, record):
        # If already JSON, return as-is
        if record.msg.startswith('{'):
            return record.msg
        
        # Otherwise, create structured log
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)
