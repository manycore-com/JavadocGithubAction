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


def is_trivial_method(method_node, source_code):
    """Check if a method is trivial (too simple to warrant Javadoc documentation).

    A trivial method is one that contains only simple operations without complex logic.
    Examples: methods that only set fields to null, single-statement methods,
    simple delegating methods, methods with only basic assertions, or test setup/teardown.

    Args:
        method_node: Tree-sitter node (method_declaration)
        source_code: Full source code string

    Returns:
        bool: True if method is trivial and should skip documentation
    """
    # Check for test setup/teardown annotations - these are always trivial
    # (standard test infrastructure that doesn't need documentation)
    method_text = get_node_text(method_node, source_code)
    test_infrastructure_annotations = [
        '@BeforeEach', '@Before',      # JUnit setup
        '@AfterEach', '@After',        # JUnit teardown
        '@BeforeAll', '@BeforeClass',  # Static setup
        '@AfterAll', '@AfterClass',    # Static teardown
    ]

    for annotation in test_infrastructure_annotations:
        if annotation in method_text:
            return True  # Test setup/teardown = trivial

    # Find the method body
    body_node = None
    for child in method_node.children:
        if child.type == 'block':
            body_node = child
            break

    if not body_node:
        return True  # No body = trivial (abstract/interface method)

    # Count different types of nodes
    control_flow_nodes = 0
    statements = []
    null_assignments = 0
    simple_assertions = 0

    def analyze_node(node, depth=0):
        nonlocal control_flow_nodes, null_assignments, simple_assertions

        # Control flow structures indicate complexity
        if node.type in ['if_statement', 'for_statement', 'while_statement',
                         'do_statement', 'switch_expression', 'try_statement',
                         'enhanced_for_statement']:
            control_flow_nodes += 1

        # Check for null assignments (e.g., "x = null")
        if node.type == 'assignment_expression':
            # Check if right side is null
            right_side = None
            for child in node.children:
                if child.type == 'null_literal':
                    null_assignments += 1
                    break

        # Check for assertions (common test patterns)
        if node.type == 'expression_statement':
            for child in node.children:
                if child.type == 'method_invocation':
                    method_text = get_node_text(child, source_code)
                    # Common test assertions (JUnit 4/5, TestNG, AssertJ)
                    assertion_patterns = [
                        'assertEquals(', 'assertNotEquals(', 'assertTrue(',
                        'assertFalse(', 'assertNull(', 'assertNotNull(',
                        'assertThat(', 'assertThrows(', 'assertSame(',
                        'assertNotSame(', 'assertArrayEquals(', 'fail(',
                        'expect(', 'verify(', 'assert(',
                    ]
                    if any(assertion in method_text for assertion in assertion_patterns):
                        # Count all assertions, even complex ones
                        # (tests often have nested method calls in assertions)
                        simple_assertions += 1

        # Recurse into children
        for child in node.children:
            analyze_node(child, depth + 1)

    # Collect statements (excluding braces)
    for child in body_node.children:
        if child.type not in ['{', '}']:
            statements.append(child)
            analyze_node(child)

    # Check if this is a @Test method with simple iteration pattern
    # (common in tests that loop through test data with assertions)
    is_test_method = '@Test' in method_text

    # Trivial if:
    # 1. Has control flow but is a simple test iteration pattern
    if control_flow_nodes > 0:
        # @Test methods with assertions = likely trivial test data iteration
        # unless they have complex business logic
        if is_test_method and simple_assertions >= 1:
            # Check if it's primarily iteration/validation, not complex business logic
            has_complex_logic = False
            for stmt in statements:
                stmt_text = get_node_text(stmt, source_code)
                # Look for complex operations beyond simple loops + assertions + calls
                complex_indicators = [
                    'new Thread', 'synchronized', '.wait(', '.notify(',
                    'volatile', 'atomic', 'lock', 'semaphore',
                    'Thread.sleep', 'CompletableFuture', 'ExecutorService',
                    'Stream.', 'parallel()', 'fork()', 'join(',
                ]
                if any(indicator in stmt_text for indicator in complex_indicators):
                    has_complex_logic = True
                    break

            # Simple test iteration/validation pattern = trivial
            if not has_complex_logic:
                return True

        # Otherwise, control flow = NOT trivial (complex logic)
        return False

    # 2. Single statement = trivial
    if len(statements) == 1:
        return True

    # 3. Mostly null assignments = trivial cleanup method
    #    (e.g., tearDown with null assignments + logging/println calls)
    if null_assignments >= len(statements) * 0.5:  # At least 50% are null assignments
        return True

    # 4. Only simple assertions (1-3 statements) = trivial test
    if simple_assertions > 0 and simple_assertions >= len(statements) - 1 and len(statements) <= 3:
        return True

    # 5. Very few statements (2-3) with no complex operations = likely trivial
    if len(statements) <= 3:
        # Check if statements are just simple assignments or method calls
        complex_operations = 0
        for stmt in statements:
            stmt_text = get_node_text(stmt, source_code)
            # Look for operators that indicate complexity (not just print/log calls)
            if any(op in stmt_text for op in ['+', '-', '*', '/', '%', '&&', '||', '?', ':']):
                # Exclude simple operations in print statements
                if 'println' not in stmt_text and 'log' not in stmt_text.lower():
                    complex_operations += 1

        # If no complex operations in simple method, it's trivial
        if complex_operations == 0:
            return True

    # 6. More than 5 statements but mostly trivial operations
    if len(statements) <= 10:
        # Count trivial operations (null assignments, simple calls)
        trivial_operations = null_assignments
        for stmt in statements:
            stmt_text = get_node_text(stmt, source_code)
            # Count simple logging/printing as trivial
            if any(call in stmt_text for call in ['println', 'print(', 'log.', 'logger.']):
                trivial_operations += 1

        # If 80%+ are trivial operations = trivial method
        if trivial_operations >= len(statements) * 0.8:
            return True

    return False


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

    # Skip if it's trivial (simple logic that doesn't need documentation)
    if is_trivial_method(method_node, source_code):
        return True

    return False


def should_skip_class(lines):
    """Determine if a class should be skipped from Javadoc generation based on file size."""
    # Skip if the entire Java file is shorter than minimum threshold
    if len(lines) < MIN_FILE_LINES:
        return True

    return False
