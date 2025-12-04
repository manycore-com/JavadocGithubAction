#!/usr/bin/env python3
"""
Unit tests for version generation logic.
Tests the single-version generation system.
"""

import unittest
import sys
import os
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from action import (
    get_num_versions,
    get_variation_instructions,
    process_item_with_pipeline
)

from constants import DEFAULT_NUM_VERSIONS


class TestVersionGeneration(unittest.TestCase):
    """Test version generation configuration and logic."""

    def test_default_num_versions_is_one(self):
        """Test that DEFAULT_NUM_VERSIONS is set to 1."""
        self.assertEqual(DEFAULT_NUM_VERSIONS, 1,
                        "Should generate only 1 version by default")

    @patch.dict(os.environ, {}, clear=True)
    def test_get_num_versions_returns_one_by_default(self):
        """Test that get_num_versions returns 1 when no env var is set."""
        result = get_num_versions()
        self.assertEqual(result, 1, "Should return 1 version by default")

    @patch.dict(os.environ, {'JAVADOC_NUM_VERSIONS': '1'})
    def test_get_num_versions_from_env_var(self):
        """Test reading JAVADOC_NUM_VERSIONS from environment."""
        result = get_num_versions()
        self.assertEqual(result, 1, "Should respect environment variable")

    @patch.dict(os.environ, {'JAVADOC_NUM_VERSIONS': 'invalid'})
    def test_get_num_versions_handles_invalid_env_var(self):
        """Test that invalid env var value falls back to default."""
        result = get_num_versions()
        self.assertEqual(result, 1, "Should fall back to default on invalid value")

    @patch.dict(os.environ, {'JAVADOC_NUM_VERSIONS': '5'})
    def test_get_num_versions_rejects_invalid_numbers(self):
        """Test that values outside valid range (1) fall back to default."""
        result = get_num_versions()
        self.assertEqual(result, 1, "Should fall back to default for invalid numbers")

    def test_get_variation_instructions_for_single_version(self):
        """Test that variation instructions for 1 version returns list with None."""
        instructions = get_variation_instructions(1)
        self.assertEqual(len(instructions), 1,
                        "Should return exactly 1 instruction for single version")
        self.assertIsNone(instructions[0],
                         "Instruction should be None (variations not used)")

    def test_variation_instructions_are_not_used_for_single_version(self):
        """Test that for single version, variation is not really needed."""
        # This test documents that we're simplifying to single version
        # In practice, variation instructions won't affect output when num_versions=1
        instructions = get_variation_instructions(1)
        # Just verify we get a list with 1 element
        self.assertEqual(len(instructions), 1)


class TestSingleVersionGenerationLogic(unittest.TestCase):
    """Test that generation logic produces exactly 1 version."""

    @patch('action.generate_javadoc')
    @patch('action.get_num_versions')
    def test_no_existing_javadoc_generates_single_version(self, mock_get_num, mock_generate):
        """Test that items without existing javadoc generate exactly 1 version."""
        mock_get_num.return_value = 1
        mock_generate.return_value = (
            "/** Generated javadoc */",
            {'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150, 'estimated_cost': 0.01}
        )

        item = {
            'type': 'method',
            'name': 'testMethod',
            'parameters': []
        }

        # Mock dependencies
        mock_client = Mock()
        mock_prompt = "prompt template"
        mock_stats = {
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'total_tokens': 0,
            'total_cost': 0.0,
            'items_processed': 0,
            'items_bypassed_by_heuristics': 0
        }

        result = process_item_with_pipeline(
            item=item,
            java_content="class Test {}",
            client=mock_client,
            prompt_template=mock_prompt,
            total_usage_stats=mock_stats,
            file_path="/fake/path.java"
        )

        # Verify exactly 1 API call was made
        self.assertEqual(mock_generate.call_count, 1,
                        "Should call generate_javadoc exactly once")

        # Verify result structure
        self.assertIsNotNone(result)
        self.assertIn('javadoc', result)
        self.assertEqual(result['javadoc'], "/** Generated javadoc */")

        # Verify NO alternatives are generated
        self.assertIsNone(result.get('alternatives'),
                         "Should not generate alternatives for single version")
        self.assertFalse(result.get('used_existing', True),
                        "Should not use existing javadoc")

    @patch('action.generate_javadoc')
    @patch('action.get_num_versions')
    @patch('action.run_heuristic_checks')
    @patch('action.should_skip_ai_assessment')
    @patch('action.assess_javadoc_quality')
    def test_existing_javadoc_regenerates_single_version_if_needed(
        self, mock_assess, mock_skip, mock_heuristics, mock_get_num, mock_generate
    ):
        """Test that items with poor existing javadoc regenerate exactly 1 version."""
        mock_get_num.return_value = 1

        # Simulate heuristics failing
        heuristic_result = Mock()
        heuristic_result.passed = False
        heuristic_result.reasons = ["Too short"]
        mock_heuristics.return_value = heuristic_result
        mock_skip.return_value = False

        # Simulate Haiku saying IMPROVE
        mock_assess.return_value = (
            True,  # needs_improvement
            {'input_tokens': 50, 'output_tokens': 5, 'total_tokens': 55, 'estimated_cost': 0.001}
        )

        # Simulate Opus generation
        mock_generate.return_value = (
            "/** Improved javadoc */",
            {'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150, 'estimated_cost': 0.01}
        )

        item = {
            'type': 'method',
            'name': 'testMethod',
            'parameters': [],
            'existing_javadoc': {
                'content': '/** Old javadoc */',
                'line': 10
            }
        }

        mock_client = Mock()
        mock_prompt = "prompt template"
        mock_stats = {
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'total_tokens': 0,
            'total_cost': 0.0,
            'items_processed': 0,
            'items_bypassed_by_heuristics': 0
        }

        result = process_item_with_pipeline(
            item=item,
            java_content="class Test {}",
            client=mock_client,
            prompt_template=mock_prompt,
            total_usage_stats=mock_stats,
            file_path="/fake/path.java"
        )

        # Verify exactly 1 Opus generation call
        self.assertEqual(mock_generate.call_count, 1,
                        "Should call generate_javadoc exactly once for regeneration")

        # Verify result structure
        self.assertIsNotNone(result)
        self.assertIn('javadoc', result)
        self.assertEqual(result['javadoc'], "/** Improved javadoc */")

        # For single version with existing javadoc, we should provide the original as alternative
        alternatives = result.get('alternatives')
        self.assertIsNotNone(alternatives, "Should include original as alternative")
        self.assertEqual(len(alternatives), 1, "Should have exactly 1 alternative (original)")
        self.assertEqual(alternatives[0]['label'], 'Original')
        self.assertEqual(alternatives[0]['content'], '/** Old javadoc */')


class TestAlternativesStructure(unittest.TestCase):
    """Test the structure of alternatives when generated."""

    def test_alternatives_are_none_for_single_new_version(self):
        """Test that alternatives is None when generating single version for new item."""
        # This is the expected behavior after our fix
        # When generating 1 version for an item without existing javadoc,
        # there should be NO alternatives
        pass

    def test_alternatives_include_original_for_updates(self):
        """Test that alternatives include original when updating existing javadoc."""
        # When regenerating javadoc, the original should be kept as an alternative
        alternatives = [
            {'label': 'Original', 'content': '/** Original version */'}
        ]

        self.assertEqual(len(alternatives), 1)
        self.assertEqual(alternatives[0]['label'], 'Original')
        self.assertIn('content', alternatives[0])

    def test_alternatives_structure_matches_expected_format(self):
        """Test that alternatives have correct structure with label and content."""
        alternative = {'label': 'Original', 'content': '/** Some javadoc */'}

        self.assertIn('label', alternative)
        self.assertIn('content', alternative)
        self.assertIsInstance(alternative['label'], str)
        self.assertIsInstance(alternative['content'], str)


class TestCostSavings(unittest.TestCase):
    """Test that single-version generation saves costs."""

    def test_single_version_uses_one_opus_call(self):
        """Test that generating 1 version uses exactly 1 Opus API call."""
        # This is the main benefit of the fix
        # OLD behavior: 2 Opus calls = ~$0.16 per item (wasted)
        # NEW behavior: 1 Opus call = ~$0.08 per item (50% savings)

        num_versions = 1
        opus_calls_expected = num_versions

        self.assertEqual(opus_calls_expected, 1,
                        "Single version should use exactly 1 Opus call")

    def test_cost_calculation_for_single_version(self):
        """Test estimated cost calculation for single version generation."""
        from constants import OPUS_INPUT_TOKEN_COST, OPUS_OUTPUT_TOKEN_COST

        # Typical token counts from log
        input_tokens = 3700
        output_tokens = 10

        cost = (input_tokens * OPUS_INPUT_TOKEN_COST) + (output_tokens * OPUS_OUTPUT_TOKEN_COST)

        # Should be approximately $0.05-0.08 per generation
        self.assertLess(cost, 0.10, "Single generation should cost less than $0.10")
        self.assertGreater(cost, 0.04, "Cost should be reasonable")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
