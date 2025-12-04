#!/usr/bin/env python3
"""
Test script to verify logger functionality.
"""

import os
import sys

# Add the script directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logger import get_logger, LogLevel, configure_logging


def test_basic_logging():
    """Test basic logging functionality."""
    print("=" * 60)
    print("TEST 1: Basic Logging")
    print("=" * 60)

    logger = get_logger("test_basic")

    logger.info("This is an info message")
    logger.success("This is a success message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.debug("This debug message should NOT appear (default level is INFO)")

    print()


def test_debug_mode():
    """Test debug mode logging."""
    print("=" * 60)
    print("TEST 2: Debug Mode")
    print("=" * 60)

    logger = get_logger("test_debug")
    configure_logging(LogLevel.DEBUG)

    logger.debug("This debug message SHOULD appear now")
    logger.info("Info message in debug mode")

    print()


def test_file_line_annotations():
    """Test file and line annotations for warnings/errors."""
    print("=" * 60)
    print("TEST 3: File/Line Annotations")
    print("=" * 60)

    logger = get_logger("test_annotations")

    logger.warning("Warning without file/line")
    logger.warning("Warning with file only", file="TestFile.java")
    logger.warning("Warning with file and line", file="TestFile.java", line=42)

    logger.error("Error without file/line")
    logger.error("Error with file only", file="TestFile.java")
    logger.error("Error with file and line", file="TestFile.java", line=100)

    logger.notice("Notice without file/line")
    logger.notice("Notice with file and line", file="TestFile.java", line=200)

    print()


def test_groups():
    """Test collapsible groups."""
    print("=" * 60)
    print("TEST 4: Groups")
    print("=" * 60)

    logger = get_logger("test_groups")

    logger.group("Processing Files")
    logger.info("Processing file 1")
    logger.info("Processing file 2")
    logger.endgroup()

    logger.group("Validation")
    logger.success("All checks passed")
    logger.endgroup()

    print()


def test_github_actions_mode():
    """Test GitHub Actions mode (simulation)."""
    print("=" * 60)
    print("TEST 5: GitHub Actions Mode (Simulation)")
    print("=" * 60)

    # Save original value
    original_value = os.environ.get('GITHUB_ACTIONS')

    # Simulate GitHub Actions environment
    os.environ['GITHUB_ACTIONS'] = 'true'

    # Create a new logger instance to pick up the environment variable
    from logger import Logger
    logger = Logger("test_gh_actions")

    logger.info("Info message in GitHub Actions mode")
    logger.warning("Warning in GitHub Actions mode", file="Test.java", line=50)
    logger.error("Error in GitHub Actions mode", file="Test.java", line=75)
    logger.notice("Notice in GitHub Actions mode", file="Test.java", line=100)

    logger.group("GitHub Actions Group")
    logger.info("Content inside group")
    logger.endgroup()

    # Restore original value
    if original_value is None:
        os.environ.pop('GITHUB_ACTIONS', None)
    else:
        os.environ['GITHUB_ACTIONS'] = original_value

    print()


def test_separators():
    """Test separator functionality."""
    print("=" * 60)
    print("TEST 6: Separators")
    print("=" * 60)

    logger = get_logger("test_separators")

    logger.separator()
    logger.info("Default separator above")
    logger.separator(char="-", length=40)
    logger.info("Custom separator above")
    logger.separator(char="*", length=30)

    print()


def test_log_levels():
    """Test different log levels."""
    print("=" * 60)
    print("TEST 7: Log Levels")
    print("=" * 60)

    logger = get_logger("test_levels")

    print("\nSetting level to WARNING:")
    logger.set_level(LogLevel.WARNING)
    logger.debug("Debug - should NOT appear")
    logger.info("Info - should NOT appear")
    logger.warning("Warning - should appear")
    logger.error("Error - should appear")

    print("\nSetting level to ERROR:")
    logger.set_level(LogLevel.ERROR)
    logger.warning("Warning - should NOT appear")
    logger.error("Error - should appear")

    print("\nResetting to INFO:")
    logger.set_level(LogLevel.INFO)
    logger.info("Info - should appear again")

    print()


def main():
    """Run all tests."""
    print("\n")
    print("*" * 60)
    print("LOGGER FUNCTIONALITY TEST SUITE")
    print("*" * 60)
    print()

    test_basic_logging()
    test_debug_mode()
    test_file_line_annotations()
    test_groups()
    test_github_actions_mode()
    test_separators()
    test_log_levels()

    print("=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)
    print("\nPlease review the output above to verify:")
    print("  1. Messages appear with correct formatting")
    print("  2. Debug messages only appear when debug mode is enabled")
    print("  3. File/line annotations work correctly")
    print("  4. Groups work correctly")
    print("  5. GitHub Actions mode formats correctly (::error::, ::warning::, etc.)")
    print("  6. Separators appear correctly")
    print("  7. Log levels filter messages correctly")


if __name__ == "__main__":
    main()
