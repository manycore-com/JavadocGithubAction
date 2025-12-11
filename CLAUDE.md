# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A GitHub Action that automatically generates and improves Javadoc comments for Java files in pull requests using Claude AI. Uses a cost-optimized 3-stage pipeline to minimize API costs while maintaining quality.

## Commands

### Run Tests
```bash
python3 -m pytest scripts/github_action_javadoc/test_javadoc.py -v
```

### Run Single Test
```bash
python3 -m pytest scripts/github_action_javadoc/test_javadoc.py::TestClassName::test_method_name -v
```

### Local Testing on a Java File
```bash
python3 scripts/github_action_javadoc/standalone.py path/to/file.java
```

### Debug Mode with Full Pipeline
```bash
JAVADOC_DEBUG=true FORCE_AI_EVAL=true python3 scripts/github_action_javadoc/standalone.py path/to/file.java
```

### Setup Environment
```bash
pip install -r scripts/github_action_javadoc/requirements.txt
```

## Architecture

### 3-Stage Quality Pipeline

The pipeline minimizes API costs by filtering at each stage:

1. **Stage 1: Heuristic Checks** (`heuristic_checks.py`) - Free, fast rule-based checks using tree-sitter. If heuristics pass, existing Javadoc is kept and AI is bypassed entirely.

2. **Stage 2: Haiku Assessment** (`action.py:assess_javadoc_quality`) - Only runs if heuristics fail. Uses Claude Haiku to evaluate quality, returns GOOD or IMPROVE.

3. **Stage 3: Opus Generation** (`action.py:generate_javadoc`) - Only runs if Haiku says IMPROVE. Uses Claude Opus to generate improved Javadoc.

### Key Modules

- **`action.py`** - Main entry point for GitHub Action, orchestrates the 3-stage pipeline
- **`java_parser.py`** - Parses Java files using tree-sitter to extract classes/methods needing docs
- **`tree_sitter_utils.py`** - Tree-sitter wrapper functions for AST operations
- **`heuristic_checks.py`** - Stage 1 rule-based quality checks (param mismatch, missing @return, etc.)
- **`javadoc_parser.py`** - Parses existing Javadoc to extract @param, @return, description
- **`javadoc_common.py`** - Shared utilities for Javadoc insertion and file manipulation
- **`code_analyzer.py`** - Analyzes method complexity to determine if documentation needed
- **`constants.py`** - Central configuration (model names, token costs, thresholds)
- **`logger.py`** - Logging utilities

### Configuration

- **`BASE-PROMPT.md`** - Prompt template for Javadoc generation (used by Opus)
- **`ASSESSMENT-PROMPT.md`** - Prompt for quality assessment (used by Haiku)
- **`constants.py`** - Model IDs, token costs, MIN_METHOD_LINES (10), MIN_FILE_LINES (30)

### Environment Variables

- `ANTHROPIC_API_KEY` - Required for API access
- `JAVADOC_DEBUG=true` - Enable debug logging
- `FORCE_AI_EVAL=true` - Force full AI pipeline even when heuristics pass

## Key Design Decisions

- Only public classes, methods, and constructors are documented
- Methods under 10 lines are skipped (configurable via MIN_METHOD_LINES)
- Files under 30 lines skip class documentation (MIN_FILE_LINES)
- Tree-sitter is used for accurate Java parsing (handles generics, annotations properly)
- Heuristic checks run first to avoid unnecessary API calls
- Getters/setters and simple delegation methods are skipped
