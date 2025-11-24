#!/usr/bin/env python3
"""
Code analysis utilities for Java files.
Analyzes method complexity, exceptions, and determines what needs documentation.
"""

import re
from constants import MIN_METHOD_LINES, MIN_FILE_LINES


def extract_method_lines(lines, start_line):
    """Extract lines of a method/constructor by counting braces.

    Args:
        lines: List of file lines
        start_line: 1-indexed starting line number

    Returns:
        list: Lines that make up the method/constructor body
    """
    start_idx = start_line - 1

    if start_idx >= len(lines):
        return []

    brace_count = 0
    method_lines = []
    found_opening_brace = False

    for i in range(start_idx, len(lines)):
        line = lines[i]
        method_lines.append(line)

        # Count braces to find method end
        brace_count += line.count('{') - line.count('}')
        if '{' in line and not found_opening_brace:
            found_opening_brace = True

        # Stop when we've closed the method
        if found_opening_brace and brace_count <= 0:
            break

    return method_lines


def extract_implementation_code(lines, item):
    """Extract the implementation code for a method or class."""
    start_line = item.get('line', 1)

    # For methods/constructors, extract until the closing brace
    if item.get('type') in ['method', 'constructor']:
        method_lines = extract_method_lines(lines, start_line)
        return '\n'.join(method_lines)

    # For classes, just return a reasonable portion
    start_idx = start_line - 1
    return '\n'.join(lines[start_idx:start_idx + 10])


def analyze_potential_exceptions(implementation_code, item_type):
    """Analyze code to identify potential exceptions that should be documented."""
    if not implementation_code:
        return []

    analysis = []
    code_lower = implementation_code.lower()

    # Look for explicit throws
    throw_matches = re.findall(r'throw\s+new\s+(\w+)', implementation_code)
    for exception in throw_matches:
        analysis.append(f"Explicitly throws {exception}")

    # Look for array access that might cause IndexOutOfBoundsException
    if '[' in implementation_code and ']' in implementation_code:
        analysis.append("Array access - consider IndexOutOfBoundsException")

    # Look for null pointer potential
    if '.length' in code_lower or '.get(' in code_lower or '.put(' in code_lower:
        analysis.append("Object method calls - consider NullPointerException")

    # Look for arithmetic that might cause ArithmeticException
    if '/' in implementation_code:
        analysis.append("Division operation - consider ArithmeticException for division by zero")

    # Look for string operations
    if any(word in code_lower for word in ['substring', 'charAt', 'split']):
        analysis.append("String operations - consider StringIndexOutOfBoundsException")

    return analysis


def is_getter_or_setter(method_name, method_body):
    """Check if a method is a simple getter or setter."""
    # Helper to count meaningful lines (excluding braces and comments)
    def count_meaningful_lines(body):
        return len([line.strip() for line in body.split('\n')
                   if line.strip() and line.strip() not in ['{', '}']
                   and not line.strip().startswith('//')])

    # Simple getter pattern: starts with "get" or "is", has return statement
    is_getter = (method_name.startswith('get') or method_name.startswith('is')) and 'return ' in method_body
    if is_getter:
        return count_meaningful_lines(method_body) <= 2

    # Simple setter pattern: starts with "set", has assignment
    is_setter = method_name.startswith('set') and ('=' in method_body or 'this.' in method_body)
    if is_setter:
        return count_meaningful_lines(method_body) <= 2

    return False


def count_method_lines(lines, start_line, method_type='method'):
    """Count the number of lines in a method/constructor implementation."""
    # Convert to 0-indexed
    start_idx = start_line - 1

    if start_idx >= len(lines):
        return 0

    brace_count = 0
    line_count = 0
    found_opening_brace = False

    for i in range(start_idx, len(lines)):
        line = lines[i]
        line_count += 1

        # Count braces to find method end
        brace_count += line.count('{') - line.count('}')
        if '{' in line and not found_opening_brace:
            found_opening_brace = True

        # Stop when we've closed the method
        if found_opening_brace and brace_count <= 0:
            break

    return line_count


def should_skip_method(method_name, lines, start_line):
    """Determine if a method should be skipped from Javadoc generation."""
    # Count lines in the method
    line_count = count_method_lines(lines, start_line)

    # Skip if method is shorter than minimum threshold
    if line_count < MIN_METHOD_LINES:
        return True

    # Extract method body for getter/setter detection
    method_lines = []
    start_idx = start_line - 1
    brace_count = 0
    found_opening_brace = False

    for i in range(start_idx, min(len(lines), start_idx + line_count)):
        line = lines[i]
        method_lines.append(line)

        brace_count += line.count('{') - line.count('}')
        if '{' in line and not found_opening_brace:
            found_opening_brace = True

        if found_opening_brace and brace_count <= 0:
            break

    method_body = '\n'.join(method_lines)

    # Skip if it's a getter or setter
    if is_getter_or_setter(method_name, method_body):
        return True

    return False


def should_skip_class(lines):
    """Determine if a class should be skipped from Javadoc generation based on file size."""
    # Skip if the entire Java file is shorter than minimum threshold
    if len(lines) < MIN_FILE_LINES:
        return True

    return False
