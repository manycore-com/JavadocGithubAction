#!/usr/bin/env python3
"""
Common functionality for Javadoc generation scripts.
Contains shared functions used by both standalone.py and action.py.
Modified to support AI Implementation Notes inside method bodies.
"""

import os
import sys
import re
from tree_sitter import Language, Parser

# Configuration constants for Javadoc generation thresholds
MIN_METHOD_LINES = 10  # Minimum lines required to document a method
MIN_FILE_LINES = 30    # Minimum lines required to document a file
METHOD_INDENT = '    ' # Standard method body indentation

def parse_existing_javadoc(javadoc_content):
    """Parse existing Javadoc to extract @param, @return, and other tags."""
    if not javadoc_content:
        return {}
    
    lines = javadoc_content.split('\n')
    parsed = {
        'description': [],
        'params': {},
        'return': None,
        'throws': {},
        'other_tags': []
    }
    
    current_section = 'description'
    current_param = None
    
    for line in lines:
        # Remove comment markers and leading/trailing whitespace
        cleaned = re.sub(r'^\s*(/\*\*|\*/?|\s*\*/)', '', line).strip()
        
        if cleaned.startswith('@param '):
            # Extract parameter name and description
            match = re.match(r'@param\s+(\w+)\s*(.*)', cleaned)
            if match:
                param_name = match.group(1)
                param_desc = match.group(2)
                parsed['params'][param_name] = param_desc
                current_param = param_name
                current_section = 'param'
        elif cleaned.startswith('@return '):
            # Extract return description
            return_desc = re.sub(r'@return\s*', '', cleaned)
            parsed['return'] = return_desc
            current_section = 'return'
        elif cleaned.startswith('@throws ') or cleaned.startswith('@exception '):
            # Extract exception info
            match = re.match(r'@(?:throws|exception)\s+(\w+)\s*(.*)', cleaned)
            if match:
                exception_name = match.group(1)
                exception_desc = match.group(2)
                parsed['throws'][exception_name] = exception_desc
                current_section = 'throws'
        elif cleaned.startswith('@'):
            # Other tags
            parsed['other_tags'].append(cleaned)
            current_section = 'other'
        elif cleaned and current_section == 'description':
            # Part of main description
            parsed['description'].append(cleaned)
        elif cleaned and current_section == 'param' and current_param:
            # Continuation of parameter description
            parsed['params'][current_param] += ' ' + cleaned
        elif cleaned and current_section == 'return':
            # Continuation of return description
            if parsed['return']:
                parsed['return'] += ' ' + cleaned
            else:
                parsed['return'] = cleaned
    
    # Join description lines
    parsed['description'] = ' '.join(parsed['description'])
    
    return parsed

def should_update_javadoc(existing_parsed, item):
    """Determine if existing Javadoc should be updated based on implementation analysis."""
    # If no existing content, definitely update
    if not existing_parsed or not existing_parsed.get('description'):
        return True

    # Always update if it's clearly generic or placeholder content
    description = existing_parsed.get('description', '').lower()
    generic_phrases = [
        'todo', 'fixme', 'placeholder', 'default constructor',
        'getter for', 'setter for', 'returns the', 'sets the'
    ]

    if any(phrase in description for phrase in generic_phrases):
        return True

    # For classes, check if there are incorrectly used @param tags
    # Regular classes should not have @param tags - if they do, update the Javadoc
    # But records should have @param tags for their components
    if item.get('type') == 'class':
        is_record = 'record' in item.get('signature', '').lower()
        if not is_record and existing_parsed.get('params'):
            return True

    # For methods, check if we have parameter or return info that's missing
    if item.get('type') == 'method':
        # If method has parameters but no @param tags, consider updating
        has_params_without_docs = item.get('parameters') and not existing_parsed.get('params')
        if has_params_without_docs:
            return True

        # If method returns something but no @return tag, consider updating
        return_type = item.get('return_type')
        has_return_without_docs = (return_type and
                                   str(return_type) != 'void' and
                                   not existing_parsed.get('return'))
        if has_return_without_docs:
            return True

    # Otherwise, preserve existing content
    return False

def find_javadoc_for_element(lines, line_num):
    """Find existing Javadoc comment above a given line number."""
    if line_num <= 1:
        return None
    
    # Look backwards from the element line to find Javadoc
    javadoc_lines = []
    current_line = line_num - 2  # Start one line above (0-indexed)
    
    # Skip empty lines and single-line comments
    while current_line >= 0:
        line = lines[current_line].strip()
        if not line or line.startswith('//'):
            current_line -= 1
            continue
        break
    
    # Check if we found a Javadoc comment
    if current_line >= 0 and lines[current_line].strip().endswith('*/'):
        # Found end of potential Javadoc, collect it
        end_line = current_line
        
        # Go backwards to find the start
        while current_line >= 0:
            line = lines[current_line].strip()
            javadoc_lines.insert(0, lines[current_line])
            if line.startswith('/**'):
                # Found the start
                javadoc_content = '\n'.join(javadoc_lines)
                return {
                    'content': javadoc_content,
                    'parsed': parse_existing_javadoc(javadoc_content),
                    'start_line': current_line + 1,
                    'end_line': end_line + 1
                }
            current_line -= 1
    
    return None

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

    if not existing_javadoc:
        return True

    return should_update_javadoc(existing_javadoc.get('parsed', {}), item)

def should_include_method(modifiers, method_name, existing_javadoc, item, lines, line_num):
    """Determine if a method should be included for documentation.

    Args:
        modifiers: List of modifier strings
        method_name: Name of the method
        existing_javadoc: Existing Javadoc dict or None
        item: Item dictionary
        lines: List of file lines
        line_num: Line number of the method

    Returns:
        bool: True if method should be documented
    """
    if 'public' not in modifiers:
        return False

    if should_skip_method(method_name, lines, line_num):
        return False

    if not existing_javadoc:
        return True

    return should_update_javadoc(existing_javadoc.get('parsed', {}), item)

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

    if not existing_javadoc:
        return True

    return should_update_javadoc(existing_javadoc.get('parsed', {}), item)

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
    implementation_code = extract_implementation_code(lines, {'type': 'class', 'line': line_num})

    item = {
        'type': 'class',
        'name': class_name,
        'line': line_num,
        'signature': signature,
        'modifiers': modifiers,
        'documentation': None,
        'existing_javadoc': existing_javadoc,
        'implementation_code': implementation_code,
        'potential_exceptions': analyze_potential_exceptions(implementation_code, 'class')
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
    implementation_code = extract_implementation_code(lines, {'type': 'method', 'line': line_num})

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
        'potential_exceptions': analyze_potential_exceptions(implementation_code, 'method')
    }

    if should_include_method(modifiers, method_name, existing_javadoc, item, lines, line_num):
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
    implementation_code = extract_implementation_code(lines, {'type': 'constructor', 'line': line_num})

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
        'potential_exceptions': analyze_potential_exceptions(implementation_code, 'constructor')
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

def extract_prompt_from_markdown(content):
    """Extract prompt content from markdown code blocks.

    Args:
        content: Markdown content

    Returns:
        str: Extracted prompt or empty string
    """
    matches = re.findall(r'```\n(.*?)\n```', content, re.DOTALL)
    return '\n\n'.join(matches) if matches else ""

def load_prompt_file(filepath):
    """Load a single prompt file and extract content from markdown.

    Args:
        filepath: Path to prompt file

    Returns:
        str: Extracted prompt or None on failure
    """
    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return extract_prompt_from_markdown(content)
    except Exception as e:
        print(f"Warning: Could not read {filepath}: {e}", file=sys.stderr)
        return None

def merge_prompts(base_prompt, customer_prompt):
    """Merge base and customer prompts.

    Args:
        base_prompt: Base prompt string (may be None or empty)
        customer_prompt: Customer prompt string (may be None or empty)

    Returns:
        str: Merged prompt, or None if both are empty
    """
    if not base_prompt and not customer_prompt:
        return None
    if not base_prompt:
        return customer_prompt
    if not customer_prompt:
        return base_prompt
    return base_prompt + "\n\n" + customer_prompt

def get_default_prompt():
    """Get the default hardcoded prompt template.

    Returns:
        str: Default prompt template
    """
    return """You are a Javadoc generator. Generate ONLY a Javadoc comment block for this Java {item_type}:

Name: {item_name}
Signature: {item_signature}

IMPLEMENTATION CODE:
{implementation_code}

{existing_content}

CORE RULES:
1. Your response must be EXACTLY a Javadoc comment block
2. Start with /** on the first line
3. End with */ on the last line
4. No explanatory text before or after
5. No "Here is..." or "I notice..." or any conversational text
6. Include @param tags for all parameters (if any)
7. Include @return tag for non-void methods
8. Include @throws tags for all exceptions that can be thrown
9. Write clear, concise descriptions based on what the code ACTUALLY does
10. Use proper grammar and punctuation

GENERATE ONLY THE JAVADOC COMMENT BLOCK NOW:
"""

def load_prompt_template():
    """Load and merge prompt templates from BASE-PROMPT.md and CUSTOMER-PROMPT.md.

    CUSTOMER-PROMPT.md takes precedence over BASE-PROMPT.md.
    Falls back to legacy CLAUDE-PROMPT.md if the new files don't exist.

    Returns:
        str: Prompt template
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    base_prompt = load_prompt_file(os.path.join(script_dir, 'BASE-PROMPT.md'))
    customer_prompt = load_prompt_file(os.path.join(script_dir, 'CUSTOMER-PROMPT.md'))

    merged_prompt = merge_prompts(base_prompt, customer_prompt)
    if merged_prompt:
        return merged_prompt

    legacy_prompt = load_prompt_file(os.path.join(script_dir, 'CLAUDE-PROMPT.md'))
    if legacy_prompt:
        return legacy_prompt

    return get_default_prompt()

def extract_javadoc_from_response(response_text):
    """Extract both the Javadoc comment block and AI implementation notes from Claude's response.
    
    Returns a dict with 'javadoc' and 'implementation_notes' keys.
    """
    lines = response_text.split('\n')
    javadoc_lines = []
    implementation_lines = []
    in_javadoc = False
    in_implementation = False
    
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
        # Look for implementation notes after Javadoc
        elif not in_javadoc and (line.strip().startswith('/* AI Implementation Notes:') or 
                                  line.strip().startswith('/*AI Implementation Notes:')):
            in_implementation = True
            implementation_lines.append(line)
        # Continue capturing implementation notes
        elif in_implementation:
            implementation_lines.append(line)
            if line.strip().endswith('*/'):
                in_implementation = False
    
    # Build the result dictionary
    result = {
        'javadoc': '\n'.join(javadoc_lines) if javadoc_lines else response_text.strip(),
        'implementation_notes': '\n'.join(implementation_lines) if implementation_lines else None
    }
    
    return result

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
    """Extract Javadoc and implementation notes from item data.

    Args:
        javadoc: Either a dict with 'javadoc' and 'implementation_notes' keys,
                or a string (backward compatibility)

    Returns:
        tuple: (javadoc_string, implementation_notes_string)
    """
    if isinstance(javadoc, dict):
        return javadoc.get('javadoc', ''), javadoc.get('implementation_notes', '')
    return javadoc, None

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

def insert_implementation_notes(lines, item, implementation_notes, base_indentation):
    """Insert implementation notes inside method body.

    Args:
        lines: List of file lines (modified in place)
        item: Item dictionary with line number
        implementation_notes: Implementation notes string to insert
        base_indentation: Base indentation of the method/class
    """
    method_start_line = item['line'] - 1
    brace_line = find_opening_brace(lines, method_start_line)

    if brace_line is None:
        return

    method_indentation = base_indentation + METHOD_INDENT
    impl_lines = implementation_notes.split('\n')

    insert_pos = brace_line + 1

    # Add blank line before if needed
    if insert_pos < len(lines) and lines[insert_pos].strip():
        lines.insert(insert_pos, '')
        insert_pos += 1

    # Insert implementation notes
    for impl_line in impl_lines:
        if impl_line.strip():
            indented_impl = method_indentation + impl_line.strip()
        else:
            indented_impl = ''
        lines.insert(insert_pos, indented_impl)
        insert_pos += 1

    # Add blank line after if needed
    if insert_pos < len(lines) and lines[insert_pos].strip():
        lines.insert(insert_pos, '')

def add_javadoc_to_file(java_content, items_with_javadoc):
    """Add generated Javadoc comments and implementation notes to the Java file content.

    Javadoc goes before the method/class declaration.
    Implementation notes go inside the method body, right after the opening brace.

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

        javadoc_str, implementation_notes = extract_javadoc_data(item['javadoc'])

        # Get base indentation before inserting javadoc
        insert_line = item['line'] - 1
        target_line = lines[insert_line] if insert_line < len(lines) else ""
        base_indentation = detect_indentation(target_line)

        # Insert Javadoc and track how many lines were added
        lines_added = insert_javadoc(lines, item, javadoc_str)

        # Update line number for implementation notes
        if lines_added > 0:
            item['line'] += lines_added

        # Insert implementation notes for methods and constructors
        if implementation_notes and item['type'] in ['method', 'constructor']:
            insert_implementation_notes(lines, item, implementation_notes, base_indentation)

    return '\n'.join(lines)
