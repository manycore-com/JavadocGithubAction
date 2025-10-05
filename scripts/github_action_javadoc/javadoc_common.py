#!/usr/bin/env python3
"""
Common functionality for Javadoc generation scripts.
Contains shared functions used by both standalone.py and action.py.
Modified to support AI Implementation Notes inside method bodies.
"""

import os
import sys
import re
tree_sitter = None
Language = None
Parser = None

try:
    import tree_sitter
    from tree_sitter import Language, Parser
except ImportError:
    print("Error: tree-sitter not installed. Run: pip install tree-sitter tree-sitter-java", file=sys.stderr)
    sys.exit(1)

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
    if item.get('type') == 'class':
        # Regular classes should not have @param tags - if they do, update the Javadoc
        # But records should have @param tags for their components
        is_record = 'record' in item.get('signature', '').lower()
        if not is_record and existing_parsed.get('params'):
            return True
    
    # For methods, check if we have parameter or return info that's missing
    if item.get('type') == 'method':
        # If method has parameters but no @param tags, consider updating
        if item.get('parameters') and not existing_parsed.get('params'):
            return True
        
        # If method returns something but no @return tag, consider updating  
        if (item.get('return_type') and 
            str(item.get('return_type')) != 'void' and 
            not existing_parsed.get('return')):
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

def extract_implementation_code(lines, item):
    """Extract the implementation code for a method or class."""
    start_line = item.get('line', 1)
    start_idx = start_line - 1
    
    if start_idx >= len(lines):
        return ""
    
    # For methods/constructors, extract until the closing brace
    if item.get('type') in ['method', 'constructor']:
        brace_count = 0
        code_lines = []
        found_opening_brace = False
        
        for i in range(start_idx, len(lines)):
            line = lines[i]
            code_lines.append(line)
            
            # Count braces to find method end
            brace_count += line.count('{') - line.count('}')
            if '{' in line and not found_opening_brace:
                found_opening_brace = True
            
            # Stop when we've closed the method
            if found_opening_brace and brace_count <= 0:
                break
        
        return '\n'.join(code_lines)
    
    # For classes, just return a reasonable portion
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
    # Simple getter pattern: starts with "get" or "is", has return statement
    if (method_name.startswith('get') or method_name.startswith('is')) and 'return ' in method_body:
        # Count non-empty lines (excluding braces and simple returns)
        meaningful_lines = [line.strip() for line in method_body.split('\n') 
                          if line.strip() and not line.strip() in ['{', '}'] 
                          and not line.strip().startswith('//')]
        # Simple getter usually has just one return statement
        return len(meaningful_lines) <= 2
    
    # Simple setter pattern: starts with "set", has assignment
    if method_name.startswith('set') and ('=' in method_body or 'this.' in method_body):
        meaningful_lines = [line.strip() for line in method_body.split('\n') 
                          if line.strip() and not line.strip() in ['{', '}'] 
                          and not line.strip().startswith('//')]
        # Simple setter usually has just one assignment
        return len(meaningful_lines) <= 2
    
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
    
    # Skip if method is shorter than 10 lines
    if line_count < 10:
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
    # Skip if the entire Java file is shorter than 30 lines
    if len(lines) < 30:
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

def parse_java_file(java_content):
    """Parse Java file using tree-sitter to extract classes and methods that need Javadoc."""
    try:
        parser = get_java_parser()
        tree = parser.parse(bytes(java_content, 'utf-8'))
    except Exception as e:
        print(f"Error parsing Java file: {e}", file=sys.stderr)
        return []

    items_needing_docs = []
    lines = java_content.split('\n')
    source_bytes = java_content.encode('utf-8')

    # Find all class declarations
    class_nodes = []
    walk_tree(tree.root_node, 'class_declaration', class_nodes, java_content)
    walk_tree(tree.root_node, 'interface_declaration', class_nodes, java_content)
    walk_tree(tree.root_node, 'record_declaration', class_nodes, java_content)
    walk_tree(tree.root_node, 'enum_declaration', class_nodes, java_content)
    
    for node in class_nodes:
        line_num = get_node_line(node)
        modifiers = extract_modifiers(node, java_content)
        
        # Get class name
        class_name = None
        for child in node.children:
            if child.type == 'identifier':
                class_name = get_node_text(child, java_content)
                break
        
        if not class_name:
            continue
        
        # Build class signature
        modifiers_str = ' '.join(modifiers) if modifiers else ''
        class_type = 'class' if node.type == 'class_declaration' else node.type.replace('_declaration', '')
        class_signature = f"{modifiers_str} {class_type} {class_name}".strip()

        # Find existing Javadoc
        existing_javadoc = find_javadoc_for_element(lines, line_num)

        implementation_code = extract_implementation_code(lines, {'type': 'class', 'line': line_num})

        item = {
            'type': 'class',
            'name': class_name,
            'line': line_num,
            'signature': class_signature,
            'modifiers': modifiers,
            'documentation': None,
            'existing_javadoc': existing_javadoc,
            'implementation_code': implementation_code,
            'potential_exceptions': analyze_potential_exceptions(implementation_code, 'class')
        }

        # Only add if public, file is large enough, and needs documentation update
        # Check for public modifier (handle parsing issues with partial matches)
        is_public = any('public' in str(mod) or 'lic' in str(mod) for mod in modifiers)
        if (is_public and 
            not should_skip_class(lines) and 
            (not existing_javadoc or should_update_javadoc(existing_javadoc.get('parsed', {}), item))):
            items_needing_docs.append(item)

    # Find all method declarations
    method_nodes = []
    walk_tree(tree.root_node, 'method_declaration', method_nodes, java_content)
    
    for node in method_nodes:
        line_num = get_node_line(node)
        modifiers = extract_modifiers(node, java_content)
        
        # Get method name
        method_name = None
        for child in node.children:
            if child.type == 'identifier':
                method_name = get_node_text(child, java_content)
                break
        
        if not method_name:
            continue
        
        # Extract parameters and return type
        params = extract_parameters(node, java_content)
        return_type = extract_return_type(node, java_content)
        
        # Build method signature
        modifiers_str = ' '.join(modifiers) if modifiers else ''
        param_strings = [f"{p['type']} {p['name']}" for p in params]
        method_signature = f"{modifiers_str} {return_type} {method_name}({', '.join(param_strings)})".strip()

        # Find existing Javadoc
        existing_javadoc = find_javadoc_for_element(lines, line_num)

        implementation_code = extract_implementation_code(lines, {'type': 'method', 'line': line_num})

        item = {
            'type': 'method',
            'name': method_name,
            'line': line_num,
            'signature': method_signature,
            'modifiers': modifiers,
            'return_type': return_type,
            'parameters': params,
            'documentation': None,
            'existing_javadoc': existing_javadoc,
            'implementation_code': implementation_code,
            'potential_exceptions': analyze_potential_exceptions(implementation_code, 'method')
        }

        # Only add if public, not a getter/setter/short method, and needs documentation update
        if ('public' in modifiers and 
            not should_skip_method(method_name, lines, line_num) and 
            (not existing_javadoc or should_update_javadoc(existing_javadoc.get('parsed', {}), item))):
            items_needing_docs.append(item)

    # Find all constructor declarations
    constructor_nodes = []
    walk_tree(tree.root_node, 'constructor_declaration', constructor_nodes, java_content)
    
    for node in constructor_nodes:
        line_num = get_node_line(node)
        modifiers = extract_modifiers(node, java_content)
        
        # Get constructor name
        constructor_name = None
        for child in node.children:
            if child.type == 'identifier':
                constructor_name = get_node_text(child, java_content)
                break
        
        if not constructor_name:
            continue
        
        # Extract parameters
        params = extract_parameters(node, java_content)
        
        # Build constructor signature
        modifiers_str = ' '.join(modifiers) if modifiers else ''
        param_strings = [f"{p['type']} {p['name']}" for p in params]
        constructor_signature = f"{modifiers_str} {constructor_name}({', '.join(param_strings)})".strip()

        # Find existing Javadoc
        existing_javadoc = find_javadoc_for_element(lines, line_num)

        implementation_code = extract_implementation_code(lines, {'type': 'constructor', 'line': line_num})

        item = {
            'type': 'constructor',
            'name': constructor_name,
            'line': line_num,
            'signature': constructor_signature,
            'modifiers': modifiers,
            'parameters': params,
            'documentation': None,
            'existing_javadoc': existing_javadoc,
            'implementation_code': implementation_code,
            'potential_exceptions': analyze_potential_exceptions(implementation_code, 'constructor')
        }

        # Only add if public and needs documentation update
        if 'public' in modifiers and (not existing_javadoc or should_update_javadoc(existing_javadoc.get('parsed', {}), item)):
            items_needing_docs.append(item)

    return items_needing_docs

def load_prompt_template():
    """Load and merge prompt templates from BASE-PROMPT.md and CUSTOMER-PROMPT.md.
    
    CUSTOMER-PROMPT.md takes precedence over BASE-PROMPT.md.
    Falls back to legacy CLAUDE-PROMPT.md if the new files don't exist.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_file = os.path.join(script_dir, 'BASE-PROMPT.md')
    customer_file = os.path.join(script_dir, 'CUSTOMER-PROMPT.md')
    legacy_file = os.path.join(script_dir, 'CLAUDE-PROMPT.md')
    
    def extract_prompt_from_markdown(content):
        """Extract prompt content from markdown code blocks."""
        import re
        matches = re.findall(r'```\n(.*?)\n```', content, re.DOTALL)
        return '\n\n'.join(matches) if matches else ""
    
    base_prompt = ""
    customer_prompt = ""
    
    # Try to load base prompt
    if os.path.exists(base_file):
        try:
            with open(base_file, 'r', encoding='utf-8') as f:
                base_content = f.read()
            base_prompt = extract_prompt_from_markdown(base_content)
        except Exception as e:
            print(f"Warning: Could not read base prompt: {e}", file=sys.stderr)
    
    # Try to load customer prompt
    if os.path.exists(customer_file):
        try:
            with open(customer_file, 'r', encoding='utf-8') as f:
                customer_content = f.read()
            customer_prompt = extract_prompt_from_markdown(customer_content)
        except Exception as e:
            print(f"Warning: Could not read customer prompt: {e}", file=sys.stderr)
    
    # If we have both base and customer prompts, merge them
    if base_prompt and customer_prompt:
        merged_prompt = base_prompt + "\n\n" + customer_prompt
        return merged_prompt
    
    # If we only have one of them, use it
    if base_prompt:
        return base_prompt
    if customer_prompt:
        return customer_prompt
    
    # Fall back to legacy CLAUDE-PROMPT.md if it exists
    if os.path.exists(legacy_file):
        try:
            with open(legacy_file, 'r', encoding='utf-8') as f:
                legacy_content = f.read()
            legacy_prompt = extract_prompt_from_markdown(legacy_content)
            if legacy_prompt:
                return legacy_prompt
        except Exception as e:
            print(f"Warning: Could not read legacy prompt: {e}", file=sys.stderr)
    
    # Final fallback to hardcoded default
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

def add_javadoc_to_file(java_content, items_with_javadoc):
    """Add generated Javadoc comments and implementation notes to the Java file content.
    
    Javadoc goes before the method/class declaration.
    Implementation notes go inside the method body, right after the opening brace.
    """
    lines = java_content.split('\n')
    
    # Sort items by line number in reverse order to avoid line number shifts
    sorted_items = sorted(items_with_javadoc, key=lambda x: x['line'], reverse=True)
    
    for item in sorted_items:
        if 'javadoc' not in item:
            continue
        
        # Extract Javadoc and implementation notes
        javadoc_data = item['javadoc']
        if isinstance(javadoc_data, dict):
            javadoc = javadoc_data.get('javadoc', '')
            implementation_notes = javadoc_data.get('implementation_notes', '')
        else:
            # Backward compatibility: if javadoc is a string, use it as-is
            javadoc = javadoc_data
            implementation_notes = None
        
        line_num = item['line']
        
        # First, handle the Javadoc insertion (same as before)
        insert_line = line_num - 1  # Convert to 0-indexed
        
        # Check if there's existing Javadoc to replace
        existing_javadoc = item.get('existing_javadoc')
        if existing_javadoc:
            # Remove the existing Javadoc
            start_line = existing_javadoc['start_line'] - 1  # Convert to 0-indexed
            end_line = existing_javadoc['end_line'] - 1    # Convert to 0-indexed
            
            # Remove the old Javadoc lines
            del lines[start_line:end_line + 1]
            
            # Adjust insertion point
            insert_line = start_line
        
        # Detect the indentation of the target method/class line
        target_line = lines[insert_line] if insert_line < len(lines) else ""
        indentation = ""
        for char in target_line:
            if char in [' ', '\t']:
                indentation += char
            else:
                break
        
        # Split the Javadoc into lines and apply indentation
        if javadoc:
            javadoc_lines = javadoc.split('\n')
            
            # Insert Javadoc at the correct position with proper indentation
            for i, javadoc_line in enumerate(javadoc_lines):
                # Apply indentation to each line of the Javadoc
                indented_line = indentation + javadoc_line if javadoc_line.strip() else javadoc_line
                lines.insert(insert_line + i, indented_line)
            
            # Update line numbers for implementation notes insertion
            # Account for the lines we just added
            line_num += len(javadoc_lines)
        
        # Now handle implementation notes insertion (for methods and constructors only)
        if implementation_notes and item['type'] in ['method', 'constructor']:
            # Find the opening brace of the method/constructor
            method_start_line = line_num - 1  # 0-indexed
            
            # Look for the opening brace
            brace_line = None
            for i in range(method_start_line, min(len(lines), method_start_line + 10)):
                if '{' in lines[i]:
                    brace_line = i
                    break
            
            if brace_line is not None:
                # Detect indentation inside the method (one level deeper)
                method_indentation = indentation + '    '  # Add 4 spaces for inner indentation
                
                # Split implementation notes into lines and apply indentation
                impl_lines = implementation_notes.split('\n')
                
                # Insert implementation notes after the opening brace
                insert_pos = brace_line + 1
                
                # Add a blank line before implementation notes if not already present
                if insert_pos < len(lines) and lines[insert_pos].strip():
                    lines.insert(insert_pos, '')
                    insert_pos += 1
                
                # Insert each line of implementation notes
                for impl_line in impl_lines:
                    if impl_line.strip():
                        indented_impl = method_indentation + impl_line.strip()
                    else:
                        indented_impl = ''
                    lines.insert(insert_pos, indented_impl)
                    insert_pos += 1
                
                # Add a blank line after implementation notes if not already present
                if insert_pos < len(lines) and lines[insert_pos].strip():
                    lines.insert(insert_pos, '')
    
    return '\n'.join(lines)
