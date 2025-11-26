#!/usr/bin/env python3
"""
Logging module with GitHub Actions support.

Provides structured logging with proper log levels and GitHub Actions
workflow commands for errors, warnings, and notices.

GitHub Actions Workflow Commands:
- ::error:: - Shows as red error annotation in GitHub UI
- ::warning:: - Shows as yellow warning annotation in GitHub UI
- ::notice:: - Shows as blue notice annotation in GitHub UI
- ::group:: / ::endgroup:: - Collapsible log sections

Usage:
    from logger import get_logger

    logger = get_logger(__name__)
    logger.info("Processing file")
    logger.warning("Potential issue detected")
    logger.error("Failed to process")
"""

import sys
import os
from enum import Enum
from typing import Optional


class LogLevel(Enum):
    """Log levels for structured logging."""
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3


class Logger:
    """
    Logger with GitHub Actions support.

    Automatically detects if running in GitHub Actions environment
    and formats messages accordingly.
    """

    def __init__(self, name: str, level: LogLevel = LogLevel.INFO):
        """
        Initialize logger.

        Args:
            name: Logger name (typically module name)
            level: Minimum log level to display
        """
        self.name = name
        self.level = level
        self.is_github_actions = os.environ.get('GITHUB_ACTIONS') == 'true'
        self._group_stack = []

    def _should_log(self, level: LogLevel) -> bool:
        """Check if message at given level should be logged."""
        return level.value >= self.level.value

    def _format_message(self, message: str, prefix: str = "") -> str:
        """Format log message with optional prefix."""
        if prefix:
            return f"{prefix} {message}"
        return message

    def debug(self, message: str):
        """Log debug message (only in DEBUG mode)."""
        if self._should_log(LogLevel.DEBUG):
            formatted = self._format_message(message, "[DEBUG]")
            print(formatted, file=sys.stdout)

    def info(self, message: str):
        """Log informational message."""
        if self._should_log(LogLevel.INFO):
            print(message, file=sys.stdout)

    def success(self, message: str):
        """Log success message (info level with checkmark)."""
        if self._should_log(LogLevel.INFO):
            formatted = f"✅ {message}"
            print(formatted, file=sys.stdout)

    def warning(self, message: str, file: Optional[str] = None, line: Optional[int] = None):
        """
        Log warning message.

        Args:
            message: Warning message
            file: Optional file path for GitHub Actions annotation
            line: Optional line number for GitHub Actions annotation
        """
        if self._should_log(LogLevel.WARNING):
            if self.is_github_actions:
                # GitHub Actions workflow command
                annotation = "::warning"
                if file:
                    annotation += f" file={file}"
                if line:
                    annotation += f",line={line}"
                annotation += f"::{message}"
                print(annotation, file=sys.stdout)
            else:
                formatted = f"⚠️  {message}"
                print(formatted, file=sys.stderr)

    def error(self, message: str, file: Optional[str] = None, line: Optional[int] = None):
        """
        Log error message.

        Args:
            message: Error message
            file: Optional file path for GitHub Actions annotation
            line: Optional line number for GitHub Actions annotation
        """
        if self._should_log(LogLevel.ERROR):
            if self.is_github_actions:
                # GitHub Actions workflow command
                annotation = "::error"
                if file:
                    annotation += f" file={file}"
                if line:
                    annotation += f",line={line}"
                annotation += f"::{message}"
                print(annotation, file=sys.stdout)
            else:
                formatted = f"❌ {message}"
                print(formatted, file=sys.stderr)

    def notice(self, message: str, file: Optional[str] = None, line: Optional[int] = None):
        """
        Log notice message (GitHub Actions only, falls back to info).

        Args:
            message: Notice message
            file: Optional file path for GitHub Actions annotation
            line: Optional line number for GitHub Actions annotation
        """
        if self._should_log(LogLevel.INFO):
            if self.is_github_actions:
                # GitHub Actions workflow command
                annotation = "::notice"
                if file:
                    annotation += f" file={file}"
                if line:
                    annotation += f",line={line}"
                annotation += f"::{message}"
                print(annotation, file=sys.stdout)
            else:
                formatted = f"ℹ️  {message}"
                print(formatted, file=sys.stdout)

    def group(self, title: str):
        """
        Start a collapsible group in GitHub Actions logs.

        Args:
            title: Group title
        """
        self._group_stack.append(title)
        if self.is_github_actions:
            print(f"::group::{title}", file=sys.stdout)
        else:
            print(f"\n{'='*60}", file=sys.stdout)
            print(title, file=sys.stdout)
            print('='*60, file=sys.stdout)

    def endgroup(self):
        """End the current collapsible group."""
        if self._group_stack:
            self._group_stack.pop()
            if self.is_github_actions:
                print("::endgroup::", file=sys.stdout)

    def separator(self, char: str = "=", length: int = 60):
        """Print a separator line."""
        if self._should_log(LogLevel.INFO):
            print(char * length, file=sys.stdout)

    def set_level(self, level: LogLevel):
        """Change the minimum log level."""
        self.level = level


# Global logger instance
_default_logger: Optional[Logger] = None


def get_logger(name: str = "javadoc", level: Optional[LogLevel] = None) -> Logger:
    """
    Get or create a logger instance.

    Args:
        name: Logger name (typically module name)
        level: Optional log level (defaults to INFO, or DEBUG if JAVADOC_DEBUG env var is set)

    Returns:
        Logger instance
    """
    global _default_logger

    if _default_logger is None:
        # Determine log level from environment
        if level is None:
            if os.environ.get('JAVADOC_DEBUG') == 'true':
                level = LogLevel.DEBUG
            else:
                level = LogLevel.INFO

        _default_logger = Logger(name, level)

    return _default_logger


def configure_logging(level: LogLevel):
    """
    Configure global logging level.

    Args:
        level: Log level to set
    """
    logger = get_logger()
    logger.set_level(level)
