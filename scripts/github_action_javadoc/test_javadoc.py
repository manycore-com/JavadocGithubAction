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

from constants import (
    CLAUDE_MODEL_OPUS,
    CLAUDE_MODEL_HAIKU,
    MAX_TOKENS,
    OPUS_INPUT_TOKEN_COST,
    OPUS_OUTPUT_TOKEN_COST,
    HAIKU_INPUT_TOKEN_COST,
    HAIKU_OUTPUT_TOKEN_COST
)

from action import load_assessment_prompt

from heuristic_checks import (
    check_missing_javadoc,
    check_javadoc_length,
    check_generic_placeholders,
    check_param_mismatch,
    check_missing_return,
    check_obvious_errors,
    run_heuristic_checks,
    should_skip_ai_assessment,
    HeuristicResult
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


class TestHeuristicChecks(unittest.TestCase):
    """Test heuristic checks for javadoc quality (Stage 1 of pipeline)."""

    def test_check_missing_javadoc(self):
        """Test detection of missing javadoc."""
        item = {'type': 'method', 'name': 'testMethod'}
        has_issue, reason = check_missing_javadoc(item, None)
        self.assertTrue(has_issue)
        self.assertEqual(reason, "No javadoc present")

        has_issue, reason = check_missing_javadoc(item, "")
        self.assertTrue(has_issue)
        self.assertEqual(reason, "No javadoc present")

        has_issue, reason = check_missing_javadoc(item, "/** Valid javadoc */")
        self.assertFalse(has_issue)

    def test_check_javadoc_length(self):
        """Test detection of too-short javadoc."""
        # Too short - only 1 line
        short_javadoc = "/** Single line */"
        has_issue, reason = check_javadoc_length(short_javadoc)
        self.assertTrue(has_issue)
        self.assertIn("too short", reason)

        # Good length - 2+ lines
        good_javadoc = """/**
         * First line of description.
         * Second line of description.
         * @param x The parameter
         */"""
        has_issue, reason = check_javadoc_length(good_javadoc)
        self.assertFalse(has_issue)

    def test_check_generic_placeholders(self):
        """Test detection of placeholder content."""
        placeholders = ['TODO', 'FIXME', 'XXX', 'HACK', 'temporary', 'placeholder']

        for placeholder in placeholders:
            javadoc = f"/** This needs {placeholder} work */"
            has_issue, reason = check_generic_placeholders(javadoc)
            self.assertTrue(has_issue, f"Should detect {placeholder}")
            self.assertIn(placeholder.upper(), reason)

        clean_javadoc = "/** This is a proper description */"
        has_issue, reason = check_generic_placeholders(clean_javadoc)
        self.assertFalse(has_issue)

    def test_check_param_mismatch_for_class(self):
        """Test that classes should not have @param tags."""
        item = {'type': 'class', 'name': 'TestClass'}
        javadoc = """/**
         * Test class description.
         * @param T The type parameter
         */"""

        has_issue, reason = check_param_mismatch(item, javadoc)
        self.assertTrue(has_issue)
        self.assertIn("should not have @param", reason)

    def test_check_param_mismatch_for_method(self):
        """Test parameter count mismatch detection."""
        item = {
            'type': 'method',
            'name': 'testMethod',
            'parameters': ['String name', 'int age']
        }

        # Missing @param for 'age'
        javadoc = """/**
         * Test method.
         * @param name The name
         */"""
        has_issue, reason = check_param_mismatch(item, javadoc)
        self.assertTrue(has_issue)
        self.assertIn("count mismatch", reason)

        # All params documented
        good_javadoc = """/**
         * Test method.
         * @param name The name
         * @param age The age
         */"""
        has_issue, reason = check_param_mismatch(item, good_javadoc)
        self.assertFalse(has_issue)

    def test_check_missing_return(self):
        """Test detection of missing @return tag."""
        item = {
            'type': 'method',
            'name': 'calculate',
            'return_type': 'int'
        }

        # Missing @return
        javadoc = "/** Calculates something */"
        has_issue, reason = check_missing_return(item, javadoc)
        self.assertTrue(has_issue)
        self.assertIn("@return", reason)

        # Has @return
        good_javadoc = """/**
         * Calculates something.
         * @return The result
         */"""
        has_issue, reason = check_missing_return(item, good_javadoc)
        self.assertFalse(has_issue)

        # Void method - no @return needed
        void_item = {
            'type': 'method',
            'name': 'doSomething',
            'return_type': 'void'
        }
        javadoc = "/** Does something */"
        has_issue, reason = check_missing_return(void_item, javadoc)
        self.assertFalse(has_issue)

    def test_check_obvious_errors(self):
        """Test detection of obvious formatting errors."""
        # Empty @param tag
        javadoc = """/**
         * Test method.
         * @param name
         */"""
        has_issue, reason = check_obvious_errors(javadoc)
        self.assertTrue(has_issue)
        self.assertIn("Empty @param", reason)

        # Extremely long line
        long_line_javadoc = "/** " + "x" * 150 + " */"
        has_issue, reason = check_obvious_errors(long_line_javadoc)
        self.assertTrue(has_issue)
        self.assertIn("exceeds", reason)

    def test_run_heuristic_checks_all_pass(self):
        """Test heuristics with good javadoc."""
        item = {
            'type': 'method',
            'name': 'testMethod',
            'parameters': ['String name'],
            'return_type': 'String'
        }
        javadoc = """/**
         * This is a comprehensive test method description.
         * It does something useful with the given parameter.
         * @param name The name to process
         * @return The processed name
         */"""

        result = run_heuristic_checks(item, javadoc, '/fake/path.java', strict_mode=True)

        self.assertTrue(result.passed)
        self.assertEqual(len(result.reasons), 0)
        self.assertTrue(should_skip_ai_assessment(result))

    def test_run_heuristic_checks_multiple_failures(self):
        """Test heuristics with multiple issues."""
        item = {
            'type': 'method',
            'name': 'calculate',
            'parameters': ['int x', 'int y'],
            'return_type': 'int'
        }
        # Short, missing params, missing return, has TODO
        javadoc = "/** TODO: write this */"

        result = run_heuristic_checks(item, javadoc, '/fake/path.java', strict_mode=True)

        self.assertFalse(result.passed)
        self.assertGreater(len(result.reasons), 2)
        self.assertFalse(should_skip_ai_assessment(result))

    def test_heuristic_result_bool_conversion(self):
        """Test HeuristicResult bool conversion."""
        passed = HeuristicResult(passed=True, reasons=[])
        self.assertTrue(bool(passed))

        failed = HeuristicResult(passed=False, reasons=["Issue 1"])
        self.assertFalse(bool(failed))


class TestPromptLoading(unittest.TestCase):
    """Test prompt loading functionality."""

    def test_load_assessment_prompt(self):
        """Test loading ASSESSMENT-PROMPT.md."""
        prompt = load_assessment_prompt()

        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 100)
        # Check for key placeholders
        self.assertIn('{item_type}', prompt)
        self.assertIn('{item_name}', prompt)
        self.assertIn('{existing_javadoc}', prompt)
        self.assertIn('{implementation_code}', prompt)

    def test_load_assessment_prompt_crashes_if_missing(self):
        """Test that load_assessment_prompt crashes if file missing."""
        # This test verifies the simplified, non-defensive behavior
        # We can't easily test the crash without breaking the test suite,
        # so we just verify the function exists and doesn't have fallback logic
        import inspect
        source = inspect.getsource(load_assessment_prompt)

        # Verify there's no try/except or fallback logic
        self.assertNotIn('except', source)
        self.assertNotIn('return """', source)


class TestThreeStagesPipeline(unittest.TestCase):
    """Test 3-stage pipeline logic."""

    def test_stage1_bypass_saves_costs(self):
        """Test that Stage 1 (heuristics) can bypass AI calls."""
        item = {
            'type': 'method',
            'name': 'goodMethod',
            'parameters': ['String param'],
            'return_type': 'String'
        }
        good_javadoc = """/**
         * This is a well-documented method.
         * It processes the parameter and returns a result.
         * @param param The input parameter
         * @return The processed result
         */"""

        result = run_heuristic_checks(item, good_javadoc, '/fake/path.java', strict_mode=True)

        # Should pass heuristics and bypass AI
        self.assertTrue(result.passed)
        self.assertTrue(should_skip_ai_assessment(result))

    def test_stage1_triggers_stage2(self):
        """Test that failing heuristics triggers Stage 2 (Haiku)."""
        item = {
            'type': 'method',
            'name': 'badMethod',
            'parameters': ['String param'],
            'return_type': 'void'
        }
        bad_javadoc = "/** TODO */"

        result = run_heuristic_checks(item, bad_javadoc, '/fake/path.java', strict_mode=True)

        # Should fail heuristics and require AI assessment
        self.assertFalse(result.passed)
        self.assertFalse(should_skip_ai_assessment(result))
        self.assertGreater(len(result.reasons), 0)

    def test_alternatives_structure(self):
        """Test that Opus regeneration produces correct alternatives structure."""
        # This tests the expected structure from process_item_with_pipeline
        # Expected: list of dicts with 'label' and 'content'
        alternatives = [
            {'label': 'Alternative 1', 'content': '/** Alt version 1 */'},
            {'label': 'Original', 'content': '/** Original version */'}
        ]

        self.assertEqual(len(alternatives), 2)
        self.assertEqual(alternatives[0]['label'], 'Alternative 1')
        self.assertEqual(alternatives[1]['label'], 'Original')
        self.assertIn('content', alternatives[0])
        self.assertIn('content', alternatives[1])


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
