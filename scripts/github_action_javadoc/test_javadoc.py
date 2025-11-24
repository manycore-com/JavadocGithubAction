#!/usr/bin/env python3
"""
Unit tests for javadoc generation scripts.
Tests for configuration constants and core functionality.
"""

import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from javadoc_common import (
    MIN_METHOD_LINES,
    MIN_FILE_LINES,
    METHOD_INDENT,
    should_skip_method,
    should_skip_class,
    parse_existing_javadoc,
    extract_javadoc_from_response,
    detect_indentation,
    count_method_lines
)

from action import (
    CLAUDE_MODEL_OPUS,
    CLAUDE_MODEL_HAIKU,
    MAX_TOKENS,
    OPUS_INPUT_TOKEN_COST,
    OPUS_OUTPUT_TOKEN_COST,
    HAIKU_INPUT_TOKEN_COST,
    HAIKU_OUTPUT_TOKEN_COST
)


class TestConfigurationConstants(unittest.TestCase):
    """Test that configuration constants are defined with expected values."""

    def test_javadoc_common_constants(self):
        """Test javadoc_common.py constants."""
        self.assertEqual(MIN_METHOD_LINES, 10)
        self.assertEqual(MIN_FILE_LINES, 30)
        self.assertEqual(METHOD_INDENT, '    ')

    def test_action_constants(self):
        """Test action.py constants."""
        self.assertEqual(CLAUDE_MODEL_OPUS, "claude-opus-4-1-20250805")
        self.assertEqual(CLAUDE_MODEL_HAIKU, "claude-3-5-haiku-20241022")
        self.assertEqual(MAX_TOKENS, 5000)
        self.assertEqual(OPUS_INPUT_TOKEN_COST, 0.000015)
        self.assertEqual(OPUS_OUTPUT_TOKEN_COST, 0.000075)
        self.assertEqual(HAIKU_INPUT_TOKEN_COST, 0.000001)
        self.assertEqual(HAIKU_OUTPUT_TOKEN_COST, 0.000005)

    def test_constants_are_not_none(self):
        """Ensure all constants are defined and not None."""
        self.assertIsNotNone(MIN_METHOD_LINES)
        self.assertIsNotNone(MIN_FILE_LINES)
        self.assertIsNotNone(METHOD_INDENT)
        self.assertIsNotNone(CLAUDE_MODEL_OPUS)
        self.assertIsNotNone(CLAUDE_MODEL_HAIKU)
        self.assertIsNotNone(MAX_TOKENS)
        self.assertIsNotNone(OPUS_INPUT_TOKEN_COST)
        self.assertIsNotNone(OPUS_OUTPUT_TOKEN_COST)
        self.assertIsNotNone(HAIKU_INPUT_TOKEN_COST)
        self.assertIsNotNone(HAIKU_OUTPUT_TOKEN_COST)


class TestMethodSkipping(unittest.TestCase):
    """Test method skipping logic using MIN_METHOD_LINES constant."""

    def test_should_skip_short_method(self):
        """Test that methods shorter than MIN_METHOD_LINES are skipped."""
        # Create a short method (5 lines)
        lines = [
            "public void shortMethod() {",
            "    int x = 1;",
            "    return x;",
            "}"
        ]
        result = should_skip_method("shortMethod", lines, 1)
        self.assertTrue(result, "Short methods should be skipped")

    def test_should_not_skip_long_method(self):
        """Test that methods >= MIN_METHOD_LINES are not skipped (if not getter/setter)."""
        # Create a method with exactly MIN_METHOD_LINES lines
        lines = [
            "public void longMethod() {",
            "    int x = 1;",
            "    int y = 2;",
            "    int z = 3;",
            "    int a = 4;",
            "    int b = 5;",
            "    int c = 6;",
            "    int d = 7;",
            "    processData(x, y, z);",
            "}"
        ]
        result = should_skip_method("longMethod", lines, 1)
        self.assertFalse(result, f"Methods with >= {MIN_METHOD_LINES} lines should not be skipped")


class TestClassSkipping(unittest.TestCase):
    """Test class skipping logic using MIN_FILE_LINES constant."""

    def test_should_skip_short_file(self):
        """Test that files shorter than MIN_FILE_LINES are skipped."""
        # Create a short file (20 lines)
        lines = ["line" for _ in range(20)]
        result = should_skip_class(lines)
        self.assertTrue(result, "Short files should be skipped")

    def test_should_not_skip_long_file(self):
        """Test that files >= MIN_FILE_LINES are not skipped."""
        # Create a file with exactly MIN_FILE_LINES lines
        lines = ["line" for _ in range(MIN_FILE_LINES)]
        result = should_skip_class(lines)
        self.assertFalse(result, f"Files with >= {MIN_FILE_LINES} lines should not be skipped")


class TestJavadocParsing(unittest.TestCase):
    """Test Javadoc parsing functionality."""

    def test_parse_existing_javadoc_with_params(self):
        """Test parsing Javadoc with @param tags."""
        javadoc = """/**
         * This is a test method.
         * @param name The name parameter
         * @param age The age parameter
         * @return The result
         */"""
        parsed = parse_existing_javadoc(javadoc)

        self.assertEqual(parsed['description'], 'This is a test method.')
        self.assertIn('name', parsed['params'])
        self.assertIn('age', parsed['params'])
        self.assertEqual(parsed['params']['name'], 'The name parameter')
        self.assertEqual(parsed['return'], 'The result')

    def test_parse_empty_javadoc(self):
        """Test parsing empty Javadoc."""
        parsed = parse_existing_javadoc("")
        self.assertEqual(parsed, {})

    def test_extract_javadoc_from_response(self):
        """Test extracting Javadoc from Claude response."""
        response = """Here is the javadoc:

/**
 * This is a test method.
 * @param x The x value
 * @return The result
 */

Some additional text after."""

        result = extract_javadoc_from_response(response)

        self.assertIsInstance(result, str)
        self.assertIn('/**', result)
        self.assertIn('@param x', result)
        self.assertIn('*/', result)


class TestIndentation(unittest.TestCase):
    """Test indentation detection."""

    def test_detect_spaces(self):
        """Test detecting space indentation."""
        line = "    public void test() {"
        indent = detect_indentation(line)
        self.assertEqual(indent, "    ")

    def test_detect_tabs(self):
        """Test detecting tab indentation."""
        line = "\t\tpublic void test() {"
        indent = detect_indentation(line)
        self.assertEqual(indent, "\t\t")

    def test_detect_no_indentation(self):
        """Test detecting no indentation."""
        line = "public void test() {"
        indent = detect_indentation(line)
        self.assertEqual(indent, "")


class TestMethodLineCounting(unittest.TestCase):
    """Test method line counting functionality."""

    def test_count_simple_method_lines(self):
        """Test counting lines in a simple method."""
        lines = [
            "public void test() {",
            "    int x = 1;",
            "    return x;",
            "}"
        ]
        count = count_method_lines(lines, 1)
        self.assertEqual(count, 4)

    def test_count_nested_braces_method_lines(self):
        """Test counting lines in a method with nested braces."""
        lines = [
            "public void test() {",
            "    if (x > 0) {",
            "        doSomething();",
            "    }",
            "    return;",
            "}"
        ]
        count = count_method_lines(lines, 1)
        self.assertEqual(count, 6)


class TestCostCalculation(unittest.TestCase):
    """Test that cost calculations use the correct constants."""

    def test_opus_cost_calculation_formula(self):
        """Test that cost calculation uses OPUS_INPUT_TOKEN_COST and OPUS_OUTPUT_TOKEN_COST."""
        input_tokens = 1000
        output_tokens = 500

        expected_cost = (input_tokens * OPUS_INPUT_TOKEN_COST) + (output_tokens * OPUS_OUTPUT_TOKEN_COST)

        # Verify the calculation
        self.assertAlmostEqual(expected_cost, 0.0525, places=4)

        # Verify constants are reasonable
        self.assertGreater(OPUS_OUTPUT_TOKEN_COST, OPUS_INPUT_TOKEN_COST,
                          "Output tokens should cost more than input tokens")

    def test_haiku_cost_calculation_formula(self):
        """Test that cost calculation uses HAIKU_INPUT_TOKEN_COST and HAIKU_OUTPUT_TOKEN_COST."""
        input_tokens = 1000
        output_tokens = 500

        expected_cost = (input_tokens * HAIKU_INPUT_TOKEN_COST) + (output_tokens * HAIKU_OUTPUT_TOKEN_COST)

        # Verify the calculation
        self.assertAlmostEqual(expected_cost, 0.0035, places=4)

        # Verify constants are reasonable
        self.assertGreater(HAIKU_OUTPUT_TOKEN_COST, HAIKU_INPUT_TOKEN_COST,
                          "Output tokens should cost more than input tokens")
        self.assertLess(HAIKU_INPUT_TOKEN_COST, OPUS_INPUT_TOKEN_COST,
                       "Haiku should be cheaper than Opus")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
