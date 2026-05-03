"""
Logging configuration for the formulas module.

This module provides centralized logging configuration for formula
validation, evaluation, and workflow execution.
"""
import logging
from typing import Optional

# Default log format
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Get or create a logger with the specified name.
    
    Args:
        name: The name of the logger (typically __name__)
        level: Optional logging level (defaults to INFO)
        
    Returns:
        A configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        if level is None:
            level = logging.INFO
        
        logger.setLevel(level)
        
        # Create console handler
        handler = logging.StreamHandler()
        handler.setLevel(level)
        
        # Create formatter
        formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(handler)
    
    return logger


def set_log_level(level: int) -> None:
    """
    Set the log level for all formula loggers.
    
    Args:
        level: The logging level (e.g., logging.DEBUG, logging.INFO)
    """
    logging.getLogger('api.formulas').setLevel(level)
