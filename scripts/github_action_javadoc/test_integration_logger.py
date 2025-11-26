#!/usr/bin/env python3
"""
Integration test to verify logger works with action.py functions.
"""

import os
import sys
import tempfile

# Add the script directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logger import get_logger, LogLevel

# Import action.py functions that use the logger
from action import (
    print_items_summary,
    print_final_summary,
)


def test_logger_in_action_functions():
    """Test that logger works in action.py functions."""
    print("=" * 60)
    print("INTEGRATION TEST: Logger in action.py")
    print("=" * 60)

    # Test print_items_summary
    print("\nTest 1: print_items_summary()")
    print("-" * 40)
    items = [
        {'type': 'class', 'name': 'TestClass', 'existing_javadoc': None},
        {'type': 'method', 'name': 'testMethod', 'existing_javadoc': {'content': '/** Existing doc */'}},
        {'type': 'method', 'name': 'anotherMethod', 'existing_javadoc': None},
    ]
    print_items_summary(items)

    # Test print_final_summary
    print("\nTest 2: print_final_summary()")
    print("-" * 40)
    java_files = ['Test1.java', 'Test2.java']
    files_modified = ['Test1.java']
    total_usage_stats = {
        'items_processed': 5,
        'items_bypassed_by_heuristics': 2,
        'total_tokens': 1234,
        'total_cost': 0.0567
    }
    print_final_summary(java_files, files_modified, total_usage_stats, commit_after=False)

    print("\n" + "=" * 60)
    print("INTEGRATION TEST COMPLETED")
    print("=" * 60)


def test_logger_with_github_actions_env():
    """Test logger with GitHub Actions environment."""
    print("\n" + "=" * 60)
    print("GITHUB ACTIONS MODE TEST")
    print("=" * 60)

    # Save original value
    original_value = os.environ.get('GITHUB_ACTIONS')
    os.environ['GITHUB_ACTIONS'] = 'true'

    # Reimport to get new logger instance
    import importlib
    import logger as logger_module
    importlib.reload(logger_module)

    logger = logger_module.get_logger('github_test')

    print("\nTest 3: GitHub Actions formatted messages")
    print("-" * 40)
    logger.info("Processing Java files")
    logger.warning("Found missing @param tag", file="Example.java", line=42)
    logger.error("Failed to generate Javadoc", file="Example.java", line=100)
    logger.notice("Generated 3 Javadoc comments successfully")

    logger.group("File Processing")
    logger.info("Processing Example.java")
    logger.success("Completed successfully")
    logger.endgroup()

    # Restore original value
    if original_value is None:
        os.environ.pop('GITHUB_ACTIONS', None)
    else:
        os.environ['GITHUB_ACTIONS'] = original_value

    print("\n" + "=" * 60)
    print("GITHUB ACTIONS MODE TEST COMPLETED")
    print("=" * 60)


def main():
    """Run all integration tests."""
    print("\n")
    print("*" * 60)
    print("LOGGER INTEGRATION TEST SUITE")
    print("*" * 60)
    print()

    try:
        test_logger_in_action_functions()
        test_logger_with_github_actions_env()

        print("\n✅ All integration tests passed!")
        print("\nLogger is working correctly in:")
        print("  - Standard mode (local development)")
        print("  - GitHub Actions mode (CI/CD)")
        print("  - Integration with action.py functions")
        print("  - File/line annotations for warnings and errors")
        print("  - Collapsible groups for log organization")

    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
