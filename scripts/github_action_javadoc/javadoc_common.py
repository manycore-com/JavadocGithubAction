#!/usr/bin/env python3
"""
Common functionality for Javadoc generation scripts.
Contains shared functions used by both standalone.py and action.py.
"""

import os
import sys
import re

# Import configuration constants from central location
from constants import MIN_METHOD_LINES, MIN_FILE_LINES, METHOD_INDENT

# Import logger
from logger import get_logger

# Import tree-sitter utilities
from tree_sitter_utils import get_java_parser, get_node_text, get_node_line, walk_tree

# Import Javadoc parsing functions
from javadoc_parser import parse_existing_javadoc, find_javadoc_for_element, should_update_javadoc

# Import code analyzer functions
from code_analyzer import (
    extract_implementation_code,
    analyze_potential_exceptions,
    should_skip_method as should_skip_method_new,
    should_skip_class,
    count_method_lines as count_method_lines_ast
)

# Initialize logger
logger = get_logger(__name__)

# Backward-compatible wrappers for tests - these parse Java to get tree-sitter nodes
def count_method_lines_legacy(lines, start_line, method_type='method'):
    """Backward-compatible wrapper for count_method_lines for tests.

    Args:
        lines: List of file lines
        start_line: 1-indexed starting line number
        method_type: Type of method (ignored, kept for compatibility)

    Returns:
        int: Number of lines in the method/constructor
    """
    # Parse the Java code to get a tree-sitter node
    from code_analyzer import count_method_lines
    java_content = '\n'.join(lines)

    try:
        parser = get_java_parser()
        tree = parser.parse(bytes(java_content, 'utf-8'))

        # Find the method/constructor node at the given line
        method_nodes = []
        constructor_nodes = []
        walk_tree(tree.root_node, 'method_declaration', method_nodes, java_content)
        walk_tree(tree.root_node, 'constructor_declaration', constructor_nodes, java_content)

        for node in method_nodes + constructor_nodes:
            node_line = get_node_line(node)
            if node_line == start_line:
                return count_method_lines(node)

        # Fallback: manual brace counting if node not found
        start_idx = start_line - 1
        if start_idx >= len(lines):
            return 0

        brace_count = 0
        line_count = 0
        found_opening_brace = False

        for i in range(start_idx, len(lines)):
            line = lines[i]
            line_count += 1

            brace_count += line.count('{') - line.count('}')
            if '{' in line and not found_opening_brace:
                found_opening_brace = True

            if found_opening_brace and brace_count <= 0:
                break

        return line_count
    except Exception:
        # Fallback if parsing fails
        start_idx = start_line - 1
        if start_idx >= len(lines):
            return 0

        brace_count = 0
        line_count = 0
        found_opening_brace = False

        for i in range(start_idx, len(lines)):
            line = lines[i]
            line_count += 1

            brace_count += line.count('{') - line.count('}')
            if '{' in line and not found_opening_brace:
                found_opening_brace = True

            if found_opening_brace and brace_count <= 0:
                break

        return line_count

# Alias for backward compatibility
count_method_lines = count_method_lines_legacy

def should_skip_method_legacy(method_name, lines, start_line):
    """Backward-compatible wrapper for should_skip_method for tests.

    Args:
        method_name: Name of the method
        lines: List of file lines
        start_line: 1-indexed starting line number

    Returns:
        bool: True if method should be skipped
    """
    java_content = '\n'.join(lines)

    try:
        parser = get_java_parser()
        tree = parser.parse(bytes(java_content, 'utf-8'))

        # Find the method node at the given line
        method_nodes = []
        walk_tree(tree.root_node, 'method_declaration', method_nodes, java_content)

        for node in method_nodes:
            node_line = get_node_line(node)
            if node_line == start_line:
                return should_skip_method_new(method_name, node, java_content)

        # Fallback: if node not found, check manually
        from code_analyzer import count_method_lines as count_method_lines_ast
        line_count = count_method_lines_legacy(lines, start_line)

        from constants import MIN_METHOD_LINES
        if line_count < MIN_METHOD_LINES:
            return True

        return False
    except Exception:
        # Fallback if parsing fails
        from constants import MIN_METHOD_LINES
        line_count = count_method_lines_legacy(lines, start_line)
        return line_count < MIN_METHOD_LINES

# Alias for backward compatibility
should_skip_method = should_skip_method_legacy

# Import Java parsing functions from java_parser module
from java_parser import parse_java_file

def extract_prompt_from_markdown(content):
    """Extract prompt content from markdown code blocks.

    Args:
        content: Markdown content

    Returns:
        str: Extracted prompt or empty string
    """
    matches = re.findall(r'```\n(.*?)\n```', content, re.DOTALL)
    return '\n\n'.join(matches) if matches else ""

def load_prompt_template():
    """Load prompt template from BASE-PROMPT.md.

    Returns:
        str: Prompt template
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_prompt_path = os.path.join(script_dir, 'BASE-PROMPT.md')

    with open(base_prompt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    return extract_prompt_from_markdown(content)

def extract_javadoc_from_response(response_text):
    """Extract the Javadoc comment block from Claude's response.

    Returns the Javadoc string.
    """
    lines = response_text.split('\n')
    javadoc_lines = []
    in_javadoc = False

    for i, line in enumerate(lines):
        # Start capturing Javadoc
        if line.strip().startswith('/**'):
            in_javadoc = True
            javadoc_lines.append(line)
        # Continue capturing Javadoc
        elif in_javadoc:
            javadoc_lines.append(line)
            if line.strip().endswith('*/'):
                in_javadoc = False
                break

    return '\n'.join(javadoc_lines) if javadoc_lines else response_text.strip()

def detect_indentation(line):
    """Detect the indentation of a line.

    Args:
        line: Line to analyze

    Returns:
        str: Indentation string (spaces/tabs)
    """
    indentation = ""
    for char in line:
        if char in [' ', '\t']:
            indentation += char
        else:
            break
    return indentation

def apply_indentation(lines, indentation):
    """Apply indentation to a list of lines.

    Args:
        lines: List of lines to indent
        indentation: Indentation string to apply

    Returns:
        list: Indented lines
    """
    indented_lines = []
    for line in lines:
        if line.strip():
            indented_lines.append(indentation + line.strip())
        else:
            indented_lines.append('')
    return indented_lines

def extract_javadoc_data(javadoc):
    """Extract Javadoc from item data.

    Args:
        javadoc: Javadoc string

    Returns:
        str: Javadoc string
    """
    return javadoc

def calculate_javadoc_insert_line(lines, item):
    """Calculate the line number where Javadoc should be inserted.

    Args:
        lines: List of file lines
        item: Item dictionary with line number and existing_javadoc info

    Returns:
        int: 0-indexed line number for insertion
    """
    insert_line = item['line'] - 1  # Convert to 0-indexed

    existing_javadoc = item.get('existing_javadoc')
    if existing_javadoc:
        start_line = existing_javadoc['start_line'] - 1
        end_line = existing_javadoc['end_line'] - 1
        del lines[start_line:end_line + 1]
        insert_line = start_line

    return insert_line

def find_opening_brace(lines, start_line, max_search=10):
    """Find the opening brace of a method/constructor.

    Args:
        lines: List of file lines
        start_line: 0-indexed line number to start searching from
        max_search: Maximum number of lines to search

    Returns:
        int: 0-indexed line number of opening brace, or None if not found
    """
    for i in range(start_line, min(len(lines), start_line + max_search)):
        if '{' in lines[i]:
            return i
    return None

def insert_javadoc(lines, item, javadoc):
    """Insert Javadoc comment before the target line.

    Args:
        lines: List of file lines (modified in place)
        item: Item dictionary with line number and existing javadoc info
        javadoc: Javadoc string to insert

    Returns:
        int: Number of lines inserted
    """
    if not javadoc:
        return 0

    insert_line = calculate_javadoc_insert_line(lines, item)
    target_line = lines[insert_line] if insert_line < len(lines) else ""
    indentation = detect_indentation(target_line)

    javadoc_lines = javadoc.split('\n')
    for i, javadoc_line in enumerate(javadoc_lines):
        indented_line = indentation + javadoc_line if javadoc_line.strip() else javadoc_line
        lines.insert(insert_line + i, indented_line)

    return len(javadoc_lines)

def add_javadoc_to_file(java_content, items_with_javadoc):
    """Add generated Javadoc comments to the Java file content.

    Javadoc goes before the method/class declaration.

    Args:
        java_content: Original Java file content
        items_with_javadoc: List of items with generated Javadoc

    Returns:
        str: Updated Java file content
    """
    lines = java_content.split('\n')
    sorted_items = sorted(items_with_javadoc, key=lambda x: x['line'], reverse=True)

    for item in sorted_items:
        if 'javadoc' not in item:
            continue

        javadoc_str = extract_javadoc_data(item['javadoc'])

        # Insert Javadoc
        insert_javadoc(lines, item, javadoc_str)

    return '\n'.join(lines)
