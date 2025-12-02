#!/usr/bin/env python3
"""
Code analysis utilities for Java files.
Analyzes method complexity, exceptions, and determines what needs documentation.
Uses tree-sitter for robust AST-based analysis.
"""

from constants import MIN_METHOD_LINES, MIN_FILE_LINES
from tree_sitter_utils import get_node_text, walk_tree


def extract_method_lines(node, source_code):
    """Extract lines of a method/constructor using tree-sitter AST.

    Args:
        node: Tree-sitter node (method_declaration or constructor_declaration)
        source_code: Full source code string

    Returns:
        list: Lines that make up the method/constructor
    """
    method_text = get_node_text(node, source_code)
    return method_text.split('\n')


def extract_implementation_code(node, source_code):
    """Extract the implementation code for a method or class using tree-sitter.

    Args:
        node: Tree-sitter node (method_declaration, constructor_declaration, or class_declaration)
        source_code: Full source code string

    Returns:
        str: The implementation code
    """
    return get_node_text(node, source_code)


def analyze_potential_exceptions(node, source_code):
    """Analyze code using tree-sitter AST to identify potential exceptions.

    Args:
        node: Tree-sitter node (method_declaration or constructor_declaration)
        source_code: Full source code string

    Returns:
        list: Potential exceptions that should be documented
    """
    if not node:
        return []

    analysis = []

    # Find explicit throw statements
    throw_nodes = []
    walk_tree(node, 'throw_statement', throw_nodes, source_code)
    for throw_node in throw_nodes:
        # Extract the exception type from the throw statement
        for child in throw_node.children:
            if child.type == 'object_creation_expression':
                for obj_child in child.children:
                    if obj_child.type == 'type_identifier':
                        exception_name = get_node_text(obj_child, source_code)
                        analysis.append(f"Explicitly throws {exception_name}")
                        break

    # Find array access expressions
    array_access_nodes = []
    walk_tree(node, 'array_access', array_access_nodes, source_code)
    if array_access_nodes:
        analysis.append("Array access - consider IndexOutOfBoundsException")

    # Find field access and method invocations (potential NullPointerException)
    field_access_nodes = []
    method_invocation_nodes = []
    walk_tree(node, 'field_access', field_access_nodes, source_code)
    walk_tree(node, 'method_invocation', method_invocation_nodes, source_code)
    if field_access_nodes or method_invocation_nodes:
        analysis.append("Object method calls - consider NullPointerException")

    # Find binary expressions with division
    binary_nodes = []
    walk_tree(node, 'binary_expression', binary_nodes, source_code)
    for binary_node in binary_nodes:
        binary_text = get_node_text(binary_node, source_code)
        if '/' in binary_text or '%' in binary_text:
            analysis.append("Division operation - consider ArithmeticException for division by zero")
            break

    # Find string method invocations
    for method_node in method_invocation_nodes:
        method_text = get_node_text(method_node, source_code)
        if any(word in method_text for word in ['substring', 'charAt', 'split']):
            analysis.append("String operations - consider StringIndexOutOfBoundsException")
            break

    return analysis


def is_getter_or_setter(method_name, method_node, source_code):
    """Check if a method is a simple getter or setter using tree-sitter AST.

    Args:
        method_name: Name of the method
        method_node: Tree-sitter node (method_declaration)
        source_code: Full source code string

    Returns:
        bool: True if method is a simple getter or setter
    """
    # Find the method body
    body_node = None
    for child in method_node.children:
        if child.type == 'block':
            body_node = child
            break

    if not body_node:
        return False

    # Count statements in the body (excluding braces)
    statements = []
    for child in body_node.children:
        if child.type not in ['{', '}']:
            statements.append(child)

    # Simple getter: starts with "get" or "is", has only a return statement
    if method_name.startswith('get') or method_name.startswith('is'):
        if len(statements) == 1 and statements[0].type == 'return_statement':
            return True

    # Simple setter: starts with "set", has only an assignment
    if method_name.startswith('set'):
        if len(statements) == 1:
            # Check if it's an expression statement with assignment
            if statements[0].type == 'expression_statement':
                for child in statements[0].children:
                    if child.type == 'assignment_expression':
                        return True

    return False


def count_method_lines(node):
    """Count the number of lines in a method/constructor using tree-sitter AST.

    Args:
        node: Tree-sitter node (method_declaration or constructor_declaration)

    Returns:
        int: Number of lines in the method/constructor
    """
    # Calculate lines from start to end point (inclusive)
    start_line = node.start_point[0]
    end_line = node.end_point[0]
    return end_line - start_line + 1


def should_skip_method(method_name, method_node, source_code):
    """Determine if a method should be skipped from Javadoc generation using tree-sitter.

    Args:
        method_name: Name of the method
        method_node: Tree-sitter node (method_declaration)
        source_code: Full source code string

    Returns:
        bool: True if method should be skipped
    """
    # Count lines in the method
    line_count = count_method_lines(method_node)

    # Skip if method is shorter than minimum threshold
    if line_count < MIN_METHOD_LINES:
        return True

    # Skip if it's a getter or setter
    if is_getter_or_setter(method_name, method_node, source_code):
        return True

    return False


def should_skip_class(lines):
    """Determine if a class should be skipped from Javadoc generation based on file size."""
    # Skip if the entire Java file is shorter than minimum threshold
    if len(lines) < MIN_FILE_LINES:
        return True

    return False
