#!/usr/bin/env python3
"""
Tree-sitter utilities for parsing Java code.
Handles AST operations and node extraction.
"""

import sys
from tree_sitter import Language, Parser


def get_java_parser():
    """Get a tree-sitter parser for Java."""
    try:
        import tree_sitter_java
        java_language = Language(tree_sitter_java.language())
    except ImportError:
        print("Error: Could not load tree-sitter-java. Please install: pip install tree-sitter-java", file=sys.stderr)
        sys.exit(1)

    parser = Parser(java_language)
    return parser


def get_node_text(node, source_code):
    """Extract the text content of a tree-sitter node."""
    return source_code[node.start_byte:node.end_byte]


def get_node_line(node):
    """Get the line number (1-indexed) of a tree-sitter node."""
    return node.start_point[0] + 1


def extract_modifiers(node, source_code):
    """Extract modifiers from a class or method declaration."""
    modifiers = []
    for child in node.children:
        if child.type == 'modifiers':
            # Found modifiers node, extract individual modifiers
            for modifier_child in child.children:
                if modifier_child.type in ['public', 'private', 'protected', 'static', 'final', 'abstract', 'synchronized', 'native', 'strictfp']:
                    modifiers.append(get_node_text(modifier_child, source_code))
        elif child.type in ['public', 'private', 'protected', 'static', 'final', 'abstract', 'synchronized', 'native', 'strictfp']:
            modifiers.append(get_node_text(child, source_code))
    return modifiers


def extract_parameters(method_node, source_code):
    """Extract parameter information from a method declaration."""
    params = []
    formal_parameters = None

    # Find formal_parameters node
    for child in method_node.children:
        if child.type == 'formal_parameters':
            formal_parameters = child
            break

    if formal_parameters:
        for child in formal_parameters.children:
            if child.type == 'formal_parameter':
                param_type = None
                param_name = None

                for param_child in child.children:
                    if param_child.type in ['type_identifier', 'generic_type', 'array_type', 'integral_type', 'floating_point_type', 'boolean_type']:
                        param_type = get_node_text(param_child, source_code)
                    elif param_child.type == 'identifier':
                        param_name = get_node_text(param_child, source_code)

                if param_type and param_name:
                    params.append({'type': param_type, 'name': param_name})

    return params


def extract_return_type(method_node, source_code):
    """Extract return type from a method declaration."""
    for child in method_node.children:
        if child.type in ['type_identifier', 'generic_type', 'array_type', 'integral_type', 'floating_point_type', 'boolean_type', 'void_type']:
            return get_node_text(child, source_code)
    return 'void'


def walk_tree(node, node_type, results, source_code):
    """Recursively walk the tree to find nodes of a specific type."""
    if node.type == node_type:
        results.append(node)

    for child in node.children:
        walk_tree(child, node_type, results, source_code)


def get_identifier_from_node(node, source_code):
    """Extract identifier (name) from a node.

    Args:
        node: Tree-sitter node
        source_code: Source code string

    Returns:
        str: Identifier name or None
    """
    for child in node.children:
        if child.type == 'identifier':
            return get_node_text(child, source_code)
    return None


def build_class_signature(modifiers, node_type, class_name):
    """Build a class signature string.

    Args:
        modifiers: List of modifier strings
        node_type: Node type (e.g., 'class_declaration')
        class_name: Name of the class

    Returns:
        str: Class signature
    """
    modifiers_str = ' '.join(modifiers) if modifiers else ''
    class_type = 'class' if node_type == 'class_declaration' else node_type.replace('_declaration', '')
    return f"{modifiers_str} {class_type} {class_name}".strip()


def build_method_signature(modifiers, return_type, method_name, params):
    """Build a method signature string.

    Args:
        modifiers: List of modifier strings
        return_type: Return type string
        method_name: Name of the method
        params: List of parameter dicts with 'type' and 'name'

    Returns:
        str: Method signature
    """
    modifiers_str = ' '.join(modifiers) if modifiers else ''
    param_strings = [f"{p['type']} {p['name']}" for p in params]
    return f"{modifiers_str} {return_type} {method_name}({', '.join(param_strings)})".strip()


def build_constructor_signature(modifiers, constructor_name, params):
    """Build a constructor signature string.

    Args:
        modifiers: List of modifier strings
        constructor_name: Name of the constructor
        params: List of parameter dicts with 'type' and 'name'

    Returns:
        str: Constructor signature
    """
    modifiers_str = ' '.join(modifiers) if modifiers else ''
    param_strings = [f"{p['type']} {p['name']}" for p in params]
    return f"{modifiers_str} {constructor_name}({', '.join(param_strings)})".strip()
