# JavadocGithubAction
Github Action to automatically add Javadoc comments

## What is it
When you create a PR, and when you do a new push to a PR, this action will run on all Java files. It will add Javadoc comments to non-trivial classes and methods.

## Architecture: 3-Stage Quality Pipeline

This action uses a cost-optimized 3-stage pipeline to minimize API costs while maintaining quality:

### Stage 1: Heuristic Checks (FREE - No API calls)
Fast, rule-based checks that identify obvious javadoc issues using **tree-sitter** for accurate code analysis:
- Missing javadoc
- Javadoc too short (< 2 lines)
- Generic placeholders (TODO, FIXME, etc.)
- @param count mismatch with actual parameters (using tree-sitter structured data)
- Missing @return for non-void methods
- Git diff analysis (recent changes detection)
- Obvious formatting errors

**Tree-sitter integration**: Heuristic checks use tree-sitter's structured AST data for accurate parameter matching, properly handling complex types like `Map<String, List<T>>`, annotations like `@NotNull`, and array types.

**If heuristics pass**: Keep existing javadoc (bypass AI entirely - maximum cost savings)

### Stage 2: Haiku Assessment (CHEAP - Only if heuristics fail)
Uses Claude Haiku to evaluate javadoc quality against comprehensive criteria.
Returns GOOD or IMPROVE decision.

### Stage 3: Opus Regeneration (EXPENSIVE - Only if Haiku says IMPROVE)
Uses Claude Opus to generate 2 new versions + keeps original (3 total versions).
All versions posted to PR for review.

## Configuration

### Prompt Files
- `scripts/github_action_javadoc/BASE-PROMPT.md` - Javadoc generation prompt (modify to change behavior)
- `scripts/github_action_javadoc/ASSESSMENT-PROMPT.md` - Quality assessment criteria for Haiku 

## How to test it locally
You need the dependencies in scripts/github_action_javadoc/requirements.txt

Feel free to create an environment in for example miniconda for it
```bash
conda create -n javadoc python=3.12
conda activate javadoc
pip install -r scripts/github_action_javadoc/requirements.txt
```

In scripts/github_action_javadoc/ you have action.py that is used by the Github Action. You also have standalone.py which you can use from the terminal:

```bash
python3 scripts/github_action_javadoc/standalone.py path/to/javafile.java
```

### Debug Flags
For testing and debugging, you can use these environment variables:

- **`JAVADOC_DEBUG=true`** - Enable debug logging to see detailed execution information
- **`FORCE_AI_EVAL=true`** - Force the full AI pipeline evaluation even when heuristics pass (useful for testing the Haiku/Opus stages)

Example with debug flags:
```bash
JAVADOC_DEBUG=true FORCE_AI_EVAL=true python3 scripts/github_action_javadoc/standalone.py path/to/javafile.java
```

## Installation

1. on your repository, go to settings. Click "Secrets and variables" on the left side, and then Actions. Under "Repository settings", click "New repository secret" and add ANTHROPIC_API_KEY (you can create one on https://console.anthropic.com/settings/keys).
2. To ensure the github Action can run, go to repositort settings, click "Actions" to the left, then "General", and "Allow all actions and reusable workflows" is enabled.
3. copy .github/workflows/github_action_javadoc.yml to your java project.
4. copy scripts/ to your java project.
