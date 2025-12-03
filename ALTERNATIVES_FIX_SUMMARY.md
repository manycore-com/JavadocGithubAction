# Fix: Display Alternatives in Debug Mode

## Problem

When running in debug mode (`python3 action.py file.java`), the system would:
1. Detect existing javadoc needing improvement
2. Run through the 3-stage pipeline
3. Generate a new version
4. Store the original as an alternative
5. **Silently overwrite the file** without showing the comparison

**Result:** User had no way to see or compare old vs new javadoc versions in debug mode.

## Root Cause

In `action.py`, alternatives were only posted to PR in GitHub Action mode:

```python
# OLD CODE - Only shows alternatives in PR mode
if config['commit_after'] and all_alternatives:
    post_alternatives_to_pr(all_alternatives)
```

When `commit_after = False` (debug mode), alternatives were **generated but never displayed**.

## Solution

Added `print_alternatives_to_console()` function that displays alternatives to console in debug mode:

```python
# NEW CODE - Shows alternatives in both modes
if all_alternatives:
    if config['commit_after']:
        # GitHub Action mode: Post alternatives to PR
        post_alternatives_to_pr(all_alternatives)
    else:
        # Debug mode: Print alternatives to console
        print_alternatives_to_console(all_alternatives)
```

## Output Example

When running in debug mode with code changes that trigger re-evaluation:

```
============================================================
ALTERNATIVE JAVADOC VERSIONS
============================================================
The AI generated alternatives for review. Compare versions below:

📁 File: test_alternatives.java

  📝 Method: calculate (line 6)

  ✅ PRIMARY VERSION (Currently Applied):
  ──────────────────────────────────────────────────────────────────────
  /**
   * Performs a mathematical calculation on the input value.
   *
   * This method applies a series of arithmetic operations to transform
   * the input value into a result. The calculation follows a fixed formula:
   * ((x + 42) * 2 + 1) * 3 - 5.
   *
   * @param x the integer value to be transformed
   * @return the result of applying the calculation formula to the input
   */
  ──────────────────────────────────────────────────────────────────────

  🔄 ORIGINAL:
  ──────────────────────────────────────────────────────────────────────
      /**
       * TODO: write this
       */
  ──────────────────────────────────────────────────────────────────────

============================================================
```

## Benefits

✅ **Transparency**: User can see what changed
✅ **Informed decisions**: Compare old vs new to decide which is better
✅ **Catch regressions**: Spot when new javadoc is worse than original
✅ **Debug workflow**: Works in single-file debug mode
✅ **No breaking changes**: PR mode still works as before

## Use Case: Code Change Detection

This is especially important when you inject code changes to trigger re-evaluation:

1. **Before:** Good javadoc exists
2. **Code change:** Add `var b = 5; i = i + b;`
3. **Pipeline runs:** Detects code change, generates new javadoc
4. **Now you see:** Both versions side-by-side
5. **You decide:** Keep new, keep original, or manually edit

## Files Changed

- `scripts/github_action_javadoc/action.py`
  - Added `print_alternatives_to_console()` function
  - Modified `main()` to call it in debug mode
  - ~45 lines added

## Testing

Tested with:
- Method with bad javadoc (`TODO: write this`)
- Pipeline detected issues via heuristics
- Haiku confirmed "IMPROVE" needed
- Opus generated new version
- **Both versions displayed to console** ✅
