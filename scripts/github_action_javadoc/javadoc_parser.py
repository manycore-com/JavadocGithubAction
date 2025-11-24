#!/usr/bin/env python3
"""
Javadoc parsing and analysis utilities.
Handles parsing existing Javadoc comments and determining if they need updates.
"""

import re


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
