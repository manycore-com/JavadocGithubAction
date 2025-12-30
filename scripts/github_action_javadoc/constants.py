#!/usr/bin/env python3
"""
Configuration constants for Javadoc generation.
Shared across all modules.
"""

# API Configuration
CLAUDE_MODEL_OPUS = "claude-opus-4-1-20250805"
CLAUDE_MODEL_HAIKU = "claude-3-5-haiku-20241022"
MAX_TOKENS = 5000

# API Cost per token (in USD)
OPUS_INPUT_TOKEN_COST = 0.000015
OPUS_OUTPUT_TOKEN_COST = 0.000075
HAIKU_INPUT_TOKEN_COST = 0.000001
HAIKU_OUTPUT_TOKEN_COST = 0.000005

# Javadoc generation thresholds
MIN_METHOD_LINES = 10  # Minimum lines required to document a method
MIN_FILE_LINES = 30    # Minimum lines required to document a file
METHOD_INDENT = '    ' # Standard method body indentation

# Version generation
# Number of versions to generate (always 1)
# Removed multi-version support as it generated duplicates without value
DEFAULT_NUM_VERSIONS = 1

# PR size limits
# Skip processing for large PRs (refactors, package moves, initial imports)
MAX_METHODS_IN_PR = 80
