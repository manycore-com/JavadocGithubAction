"""
Heuristic checks for Javadoc quality assessment (Stage 1).

This module implements fast, free heuristic checks to identify obvious
javadoc issues before expensive AI model calls. Only items that fail
heuristics will proceed to Haiku assessment.

Note: This module uses tree-sitter structured data for accurate code analysis.
Parameters are provided as dictionaries with 'type' and 'name' keys from
tree-sitter parsing, not raw strings.
"""

import re
import subprocess
from typing import Dict, List, Tuple, Optional
from javadoc_parser import parse_existing_javadoc


class HeuristicResult:
    """Result of heuristic checks with detailed failure reasons."""

    def __init__(self, passed: bool, reasons: List[str] = None):
        self.passed = passed
        self.reasons = reasons or []

    def __bool__(self):
        return self.passed

    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"HeuristicResult({status}, reasons={self.reasons})"


def check_missing_javadoc(item: Dict, existing_javadoc: Optional[str]) -> Tuple[bool, str]:
    """
    Check if javadoc is missing entirely.

    Returns (has_issue, reason)
    """
    if not existing_javadoc or len(existing_javadoc.strip()) == 0:
        return True, "No javadoc present"
    return False, ""


def check_javadoc_length(existing_javadoc: str) -> Tuple[bool, str]:
    """
    Check if javadoc is too short to be meaningful (strict mode).

    Returns (has_issue, reason)
    """
    if not existing_javadoc:
        return False, ""

    # Extract content lines (not /** or */)
    lines = []
    for line in existing_javadoc.strip().split('\n'):
        stripped = line.strip()
        if stripped and stripped != '/**' and stripped != '*/':
            # Remove leading * and whitespace
            if stripped.startswith('*'):
                stripped = stripped[1:].strip()
            if stripped:
                lines.append(stripped)

    # Count non-@ tag lines as description
    meaningful_lines = [l for l in lines if not l.startswith('@')]

    # Strict: Flag if less than 2 lines of actual description
    if len(meaningful_lines) < 2:
        return True, f"Javadoc too short ({len(meaningful_lines)} lines of description)"

    return False, ""


def check_generic_placeholders(existing_javadoc: str) -> Tuple[bool, str]:
    """
    Check for generic placeholder content (TODO, FIXME, etc.).

    Returns (has_issue, reason)
    """
    if not existing_javadoc:
        return False, ""

    javadoc_lower = existing_javadoc.lower()
    placeholders = ['todo', 'fixme', 'xxx', 'hack', 'temporary', 'placeholder']

    for placeholder in placeholders:
        if placeholder in javadoc_lower:
            return True, f"Contains placeholder: {placeholder.upper()}"

    return False, ""


def check_param_mismatch(item: Dict, existing_javadoc: str) -> Tuple[bool, str]:
    """
    Check for @param tag mismatches (strict mode).

    For classes: Should have NO @param tags
    For methods: Should have exactly one @param tag per parameter

    Returns (has_issue, reason)
    """
    if not existing_javadoc:
        return False, ""

    parsed = parse_existing_javadoc(existing_javadoc)
    param_tags = parsed.get('params', {})  # Dict: {param_name: description}

    # Check for classes with @param tags
    if item['type'] in ['class', 'interface', 'enum', 'record']:
        if param_tags:
            return True, f"Class/Interface should not have @param tags (found {len(param_tags)})"
        return False, ""

    # Check for methods with parameter mismatches
    if item['type'] in ['method', 'constructor']:
        actual_params = item.get('parameters', [])

        # Extract parameter names from tree-sitter structured data
        # actual_params is a list of dicts: [{'type': 'String', 'name': 'input'}, ...]
        param_names = []
        for param in actual_params:
            if isinstance(param, dict) and 'name' in param:
                param_names.append(param['name'])
            elif isinstance(param, str):
                # Fallback for legacy string format "Type name"
                parts = param.strip().split()
                if len(parts) >= 2:
                    param_names.append(parts[-1])

        # Strict: Check count mismatch
        if len(param_tags) != len(param_names):
            return True, f"Parameter count mismatch: {len(param_names)} params, {len(param_tags)} @param tags"

        # Strict: Check if all parameters are documented
        # param_tags is a dict, so iterating gives us the keys (param names)
        documented_params = set(param_tags.keys())
        for param_name in param_names:
            if param_name not in documented_params:
                return True, f"Parameter '{param_name}' not documented"

        # Strict: Check for documented params that don't exist
        for documented in documented_params:
            if documented not in param_names:
                return True, f"@param tag '{documented}' doesn't match any parameter"

    return False, ""


def check_missing_return(item: Dict, existing_javadoc: str) -> Tuple[bool, str]:
    """
    Check for missing @return tag on non-void methods.

    Returns (has_issue, reason)
    """
    if not existing_javadoc:
        return False, ""

    # Only check methods
    if item['type'] != 'method':
        return False, ""

    return_type = item.get('return_type', 'void')

    # Skip void methods
    if return_type == 'void':
        return False, ""

    parsed = parse_existing_javadoc(existing_javadoc)
    return_tag = parsed.get('return')

    if not return_tag or len(return_tag.strip()) < 5:
        return True, f"Missing or trivial @return tag for {return_type} method"

    return False, ""


def check_git_diff_changes(item: Dict, file_path: str) -> Tuple[bool, str]:
    """
    Check if javadoc has significant changes in recent commits.
    Uses git diff to compare with previous commit.

    Returns (has_issue, reason)
    """
    try:
        # Get the line range for this item
        start_line = item.get('start_line')
        end_line = item.get('end_line')

        if not start_line or not end_line:
            return False, ""

        # Run git diff for this file, comparing with previous commit
        # -U0 means no context lines, just the changes
        result = subprocess.run(
            ['git', 'diff', 'HEAD~1', 'HEAD', '--', file_path, '-U0'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            # No previous commit or file not in git
            return False, ""

        diff_output = result.stdout

        if not diff_output:
            return False, ""

        # Parse diff to find changes in our line range
        # Look for @@ -start,count +start,count @@ markers
        changed_lines = 0
        in_our_range = False

        for line in diff_output.split('\n'):
            if line.startswith('@@'):
                # Parse the line range: @@ -old_start,old_count +new_start,new_count @@
                match = re.search(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', line)
                if match:
                    new_start = int(match.group(3))
                    new_count = int(match.group(4)) if match.group(4) else 1
                    new_end = new_start + new_count

                    # Check if this diff chunk overlaps with our item
                    in_our_range = (new_start <= end_line and new_end >= start_line)
            elif in_our_range and (line.startswith('+') or line.startswith('-')):
                # Count changed lines within our range
                changed_lines += 1

        # Strict: Flag if more than 3 lines changed in the javadoc area
        if changed_lines > 3:
            return True, f"Significant recent changes ({changed_lines} lines changed in git diff)"

        return False, ""

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        # Git not available or error - don't fail the check
        return False, ""


def check_obvious_errors(existing_javadoc: str) -> Tuple[bool, str]:
    """
    Check for obvious errors in javadoc formatting or content.

    Returns (has_issue, reason)
    """
    if not existing_javadoc:
        return False, ""

    issues = []

    # Check for malformed tags (@ not at start of tag)
    lines = existing_javadoc.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and '@' in stripped:
            # @ symbol should only appear at line start (after *)
            after_star = stripped.lstrip('*').strip()
            if after_star and not after_star.startswith('@') and '@' in after_star:
                issues.append("Malformed @ tag")
                break

    # Check for empty tags
    if re.search(r'@param\s+\w+\s*$', existing_javadoc, re.MULTILINE):
        issues.append("Empty @param tag (no description)")

    if re.search(r'@return\s*$', existing_javadoc, re.MULTILINE):
        issues.append("Empty @return tag (no description)")

    # Check for extremely long lines (strict: >120 chars)
    for line in lines:
        stripped = line.strip().lstrip('*').strip()
        if len(stripped) > 120:
            issues.append(f"Line exceeds 120 characters ({len(stripped)} chars)")
            break

    if issues:
        return True, "; ".join(issues)

    return False, ""


def run_heuristic_checks(
    item: Dict,
    existing_javadoc: Optional[str],
    file_path: str,
    strict_mode: bool = True
) -> HeuristicResult:
    """
    Run all heuristic checks on an item with existing javadoc.

    Args:
        item: The parsed Java item (class, method, etc.)
        existing_javadoc: The existing javadoc content (or None)
        file_path: Path to the Java source file
        strict_mode: If True, use strict checks that flag more items

    Returns:
        HeuristicResult with passed=True if javadoc looks good (skip AI),
        passed=False if issues found (needs AI assessment)
    """
    reasons = []

    # Run all checks
    checks = [
        check_missing_javadoc(item, existing_javadoc),
        check_javadoc_length(existing_javadoc) if existing_javadoc else (False, ""),
        check_generic_placeholders(existing_javadoc) if existing_javadoc else (False, ""),
        check_param_mismatch(item, existing_javadoc) if existing_javadoc else (False, ""),
        check_missing_return(item, existing_javadoc) if existing_javadoc else (False, ""),
        check_git_diff_changes(item, file_path) if strict_mode else (False, ""),
        check_obvious_errors(existing_javadoc) if existing_javadoc else (False, ""),
    ]

    # Collect all failure reasons
    for has_issue, reason in checks:
        if has_issue and reason:
            reasons.append(reason)

    # If any check failed, heuristics fail (needs AI review)
    passed = len(reasons) == 0

    return HeuristicResult(passed=passed, reasons=reasons)


def should_skip_ai_assessment(heuristic_result: HeuristicResult) -> bool:
    """
    Determine if AI assessment can be skipped based on heuristic results.

    In trust mode: If heuristics pass, skip AI entirely
    In verify mode: Always run AI, but heuristics help prioritize

    Returns True if AI assessment should be skipped
    """
    return heuristic_result.passed
