#!/usr/bin/env python3
"""
Main Java file parsing module.
Parses Java files to extract classes, methods, and constructors that need documentation.
"""

import sys
from tree_sitter_utils import (
    get_java_parser,
    get_node_line,
    extract_modifiers,
    extract_parameters,
    extract_return_type,
    get_identifier_from_node,
    build_class_signature,
    build_method_signature,
    build_constructor_signature,
    walk_tree
)
from javadoc_parser import find_javadoc_for_element
from code_analyzer import (
    extract_implementation_code,
    analyze_potential_exceptions,
    should_skip_method,
    should_skip_class
)


def should_include_class(modifiers, existing_javadoc, item, lines):
    """Determine if a class should be included for documentation.

    Args:
        modifiers: List of modifier strings
        existing_javadoc: Existing Javadoc dict or None
        item: Item dictionary
        lines: List of file lines

    Returns:
        bool: True if class should be documented
    """
    is_public = any('public' in str(mod) or 'lic' in str(mod) for mod in modifiers)
    if not is_public:
        return False

    if should_skip_class(lines):
        return False

    # Always include public classes - let heuristic_checks.py decide quality
    return True


def should_include_method(modifiers, method_name, existing_javadoc, item, method_node, java_content):
    """Determine if a method should be included for documentation.

    Args:
        modifiers: List of modifier strings
        method_name: Name of the method
        existing_javadoc: Existing Javadoc dict or None
        item: Item dictionary
        method_node: Tree-sitter node (method_declaration)
        java_content: Full Java file content

    Returns:
        bool: True if method should be documented
    """
    if 'public' not in modifiers:
        return False

    if should_skip_method(method_name, method_node, java_content):
        return False

    # Always include public methods - let heuristic_checks.py decide quality
    # Previously we filtered here with should_update_javadoc, but that missed
    # quality issues like incomplete sentences that heuristics can catch
    return True


def should_include_constructor(modifiers, existing_javadoc, item):
    """Determine if a constructor should be included for documentation.

    Args:
        modifiers: List of modifier strings
        existing_javadoc: Existing Javadoc dict or None
        item: Item dictionary

    Returns:
        bool: True if constructor should be documented
    """
    if 'public' not in modifiers:
        return False

    # Always include public constructors - let heuristic_checks.py decide quality
    return True


def create_class_item(node, java_content, lines):
    """Create an item dictionary for a class node.

    Args:
        node: Tree-sitter node
        java_content: Full Java file content
        lines: List of file lines

    Returns:
        dict: Item dictionary or None if invalid
    """
    line_num = get_node_line(node)
    modifiers = extract_modifiers(node, java_content)
    class_name = get_identifier_from_node(node, java_content)

    if not class_name:
        return None

    signature = build_class_signature(modifiers, node.type, class_name)
    existing_javadoc = find_javadoc_for_element(lines, line_num)
    implementation_code = extract_implementation_code(node, java_content)

    item = {
        'type': 'class',
        'name': class_name,
        'line': line_num,
        'signature': signature,
        'modifiers': modifiers,
        'documentation': None,
        'existing_javadoc': existing_javadoc,
        'implementation_code': implementation_code,
        'potential_exceptions': analyze_potential_exceptions(node, java_content)
    }

    if should_include_class(modifiers, existing_javadoc, item, lines):
        return item
    return None


def create_method_item(node, java_content, lines):
    """Create an item dictionary for a method node.

    Args:
        node: Tree-sitter node
        java_content: Full Java file content
        lines: List of file lines

    Returns:
        dict: Item dictionary or None if invalid
    """
    line_num = get_node_line(node)
    modifiers = extract_modifiers(node, java_content)
    method_name = get_identifier_from_node(node, java_content)

    if not method_name:
        return None

    params = extract_parameters(node, java_content)
    return_type = extract_return_type(node, java_content)
    signature = build_method_signature(modifiers, return_type, method_name, params)
    existing_javadoc = find_javadoc_for_element(lines, line_num)
    implementation_code = extract_implementation_code(node, java_content)

    item = {
        'type': 'method',
        'name': method_name,
        'line': line_num,
        'signature': signature,
        'modifiers': modifiers,
        'return_type': return_type,
        'parameters': params,
        'documentation': None,
        'existing_javadoc': existing_javadoc,
        'implementation_code': implementation_code,
        'potential_exceptions': analyze_potential_exceptions(node, java_content)
    }

    if should_include_method(modifiers, method_name, existing_javadoc, item, node, java_content):
        return item
    return None


def create_constructor_item(node, java_content, lines):
    """Create an item dictionary for a constructor node.

    Args:
        node: Tree-sitter node
        java_content: Full Java file content
        lines: List of file lines

    Returns:
        dict: Item dictionary or None if invalid
    """
    line_num = get_node_line(node)
    modifiers = extract_modifiers(node, java_content)
    constructor_name = get_identifier_from_node(node, java_content)

    if not constructor_name:
        return None

    params = extract_parameters(node, java_content)
    signature = build_constructor_signature(modifiers, constructor_name, params)
    existing_javadoc = find_javadoc_for_element(lines, line_num)
    implementation_code = extract_implementation_code(node, java_content)

    item = {
        'type': 'constructor',
        'name': constructor_name,
        'line': line_num,
        'signature': signature,
        'modifiers': modifiers,
        'parameters': params,
        'documentation': None,
        'existing_javadoc': existing_javadoc,
        'implementation_code': implementation_code,
        'potential_exceptions': analyze_potential_exceptions(node, java_content)
    }

    if should_include_constructor(modifiers, existing_javadoc, item):
        return item
    return None


def extract_items_from_nodes(nodes, java_content, lines, item_creator):
    """Extract items from tree-sitter nodes using a creator function.

    Args:
        nodes: List of tree-sitter nodes
        java_content: Full Java file content
        lines: List of file lines
        item_creator: Function that creates an item from a node

    Returns:
        list: List of item dictionaries
    """
    items = []
    for node in nodes:
        item = item_creator(node, java_content, lines)
        if item:
            items.append(item)
    return items


def parse_java_file(java_content):
    """Parse Java file using tree-sitter to extract classes and methods that need Javadoc.

    Args:
        java_content: Full Java file content

    Returns:
        list: List of items needing documentation
    """
    try:
        parser = get_java_parser()
        tree = parser.parse(bytes(java_content, 'utf-8'))
    except Exception as e:
        print(f"Error parsing Java file: {e}", file=sys.stderr)
        return []

    lines = java_content.split('\n')

    # Find all class-like declarations
    class_nodes = []
    for node_type in ['class_declaration', 'interface_declaration', 'record_declaration', 'enum_declaration']:
        walk_tree(tree.root_node, node_type, class_nodes, java_content)

    # Find method declarations
    method_nodes = []
    walk_tree(tree.root_node, 'method_declaration', method_nodes, java_content)

    # Find constructor declarations
    constructor_nodes = []
    walk_tree(tree.root_node, 'constructor_declaration', constructor_nodes, java_content)

    # Extract items from nodes
    items_needing_docs = []
    items_needing_docs.extend(extract_items_from_nodes(class_nodes, java_content, lines, create_class_item))
    items_needing_docs.extend(extract_items_from_nodes(method_nodes, java_content, lines, create_method_item))
    items_needing_docs.extend(extract_items_from_nodes(constructor_nodes, java_content, lines, create_constructor_item))

    return items_needing_docs
