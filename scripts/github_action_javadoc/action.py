#!/usr/bin/env python3
"""
Enhanced action.py that properly uses BASE-PROMPT.md template with full context.
Maintains the original calling pattern while fixing the issues.
"""

import os
import re
import sys
from anthropic import Anthropic

# Import from javadoc_common as in original
from javadoc_common import (
    parse_java_file,
    load_prompt_template,
    extract_javadoc_from_response,
)


def generate_documentation_with_diagnostics(client, item):
    """Generate documentation using the BASE-PROMPT.md template properly."""
    
    print(f"\n{'='*60}")
    print(f"GENERATING FOR: {item['type']} {item['name']}")
    print('='*60)
    
    print("\n1. ITEM DETAILS:")
    print(f"   Type: {item['type']}")
    print(f"   Has JavaDoc: {item.get('has_javadoc', False)}")
    print(f"   Has Impl Notes: {item.get('has_impl_notes', False)}")
    
    # Skip if both already exist
    if item.get('has_javadoc') and item.get('has_impl_notes', False):
        print("   ✔ Already fully documented, skipping")
        return None, None
    
    # Load the prompt template from BASE-PROMPT.md
    base_template = load_prompt_template()
    
    # For classes, only generate JavaDoc
    if item['type'] == 'class':
        if item.get('has_javadoc'):
            print("   ✔ Class already has JavaDoc, skipping")
            return None, None
        
        # Format the template with actual values
        prompt = base_template.format(
            item_type='class',
            item_name=item.get('name', ''),
            item_signature=item.get('signature', ''),
            implementation_code=item.get('implementation_code', ''),
            modifiers=', '.join(item.get('modifiers', [])) if item.get('modifiers') else 'none',
            parameters='N/A for class',
            return_type='N/A for class',
            existing_content='',
            java_content=item.get('full_file_content', '')  # Add full context if available
        )
        
        print("\n2. SENDING CLASS JAVADOC REQUEST...")
        
        try:
            response = client.messages.create(
                model="claude-opus-4-1-20250805",  # Use Opus for best quality
                max_tokens=2000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            response_text = response.content[0].text
            print(f"   Response length: {len(response_text)} chars")
            javadoc = extract_javadoc(response_text)
            if javadoc:
                print("   ✔ JavaDoc extracted successfully")
            else:
                print("   ✗ Failed to extract JavaDoc")
            return javadoc, None
        except Exception as e:
            print(f"   ✗ API Error: {e}")
            return None, None
    
    # For methods/constructors
    elif item['type'] in ['method', 'constructor']:
        needs_javadoc = not item.get('has_javadoc')
        needs_impl = not item.get('has_impl_notes')
        
        print(f"\n2. NEEDS:")
        print(f"   JavaDoc: {needs_javadoc}")
        print(f"   Implementation Notes: {needs_impl}")
        
        if not needs_javadoc and not needs_impl:
            print("   ✔ Already fully documented")
            return None, None
        
        # Build existing content string if we have it
        existing_content = ""
        if item.get('existing_javadoc'):
            existing_content = f"EXISTING JAVADOC TO IMPROVE:\n{item['existing_javadoc'].get('content', '')}"
        
        # Format parameters for the template
        params_str = "None"
        if item.get('parameters'):
            params_str = ', '.join([f"{p['type']} {p['name']}" for p in item['parameters']])
        
        # Format the template with actual values
        prompt = base_template.format(
            item_type=item['type'],
            item_name=item.get('name', ''),
            item_signature=item.get('signature', ''),
            implementation_code=item.get('implementation_code', ''),  # FULL CODE, not truncated!
            modifiers=', '.join(item.get('modifiers', [])) if item.get('modifiers') else 'none',
            parameters=params_str,
            return_type=item.get('return_type', 'void'),
            existing_content=existing_content,
            java_content=item.get('full_file_content', '')  # Add full context if available
        )
        
        # Add specific request for implementation notes if needed
        if needs_impl:
            prompt += """

ADDITIONAL REQUIREMENT:
You MUST also provide implementation notes as comments that explain the algorithm:
// Implementation notes: Overall approach or algorithm used
// Step-by-step explanation of complex logic
// Performance characteristics if relevant
// Edge cases handled

Format the implementation notes to be inserted into the method body."""

        print("\n3. PROMPT CREATED using BASE-PROMPT.md template")
        print(f"   Prompt length: {len(prompt)} chars")
        print(f"   Full implementation code included: {len(item.get('implementation_code', ''))} chars")
        print("\n4. SENDING TO CLAUDE...")
        
        try:
            response = client.messages.create(
                model="claude-opus-4-1-20250805",  # Use Opus for best quality
                max_tokens=4000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            response_text = response.content[0].text
            
            print(f"\n5. CLAUDE'S RESPONSE ({len(response_text)} chars):")
            print("-" * 40)
            # Show first 500 chars of response
            print(response_text[:500])
            if len(response_text) > 500:
                print("... [truncated for display] ...")
            print("-" * 40)
            
            # Extract JavaDoc
            javadoc = None
            if needs_javadoc:
                javadoc = extract_javadoc(response_text)
                print(f"\n6. JAVADOC EXTRACTION:")
                if javadoc:
                    print(f"   ✔ Extracted {len(javadoc)} chars")
                    print(f"   First line: {javadoc.split(chr(10))[0]}")
                else:
                    print("   ✗ Failed to extract JavaDoc")
            
            # Extract implementation notes
            impl_notes = None
            if needs_impl:
                impl_notes = extract_implementation_notes_diagnostic(response_text)
                print(f"\n7. IMPLEMENTATION NOTES EXTRACTION:")
                if impl_notes:
                    print(f"   ✔ Extracted {len(impl_notes)} chars")
                    print("   Content:")
                    print(impl_notes[:200] + "..." if len(impl_notes) > 200 else impl_notes)
                else:
                    print("   ✗ Failed to extract implementation notes")
            
            return javadoc, impl_notes
            
        except Exception as e:
            print(f"\n   ✗ API Error: {e}")
            return None, None
    
    return None, None


def extract_javadoc(text):
    """Extract JavaDoc from response."""
    match = re.search(r'/\*\*.*?\*/', text, re.DOTALL)
    if match:
        return match.group(0).strip()
    return None


def extract_implementation_notes_diagnostic(text):
    """Extract implementation notes with diagnostics."""
    
    print("\n   Trying extraction patterns:")
    
    patterns = [
        (r'//\s*Implementation notes:.*?(?=\n\s*[^/]|\n\s*$|\Z)', "Pattern 1: Basic"),
        (r'//\s*Implementation notes:.*?(?=\n\s*(?:int|var|for|while|if|return|throw|\}|$))', "Pattern 2: Until keyword"),
        (r'//\s*Implementation notes:[^\n]+(?:\n\s*//[^\n]+)*', "Pattern 3: Multi-line")
    ]
    
    for pattern, description in patterns:
        print(f"   Trying {description}...")
        match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
        if match:
            notes = match.group(0).strip()
            print(f"   ✔ Matched with {description}")
            
            # Format with proper indentation
            lines = notes.split('\n')
            formatted = []
            for line in lines:
                line = line.strip()
                if line:
                    if not line.startswith('//'):
                        line = '// ' + line
                    formatted.append('    ' + line)
            return '\n'.join(formatted) if formatted else None
    
    print("   ✗ No pattern matched")
    return None


def parse_java_file_simple(file_path):
    """Parse Java file using tree-sitter from javadoc_common."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Use the sophisticated tree-sitter parser
    items = parse_java_file(content)
    
    # Enhance items with full file content for context
    for item in items:
        item['full_file_content'] = content
    
    return items


def main():
    """Main function."""
    
    if len(sys.argv) < 2:
        print("Usage: python action.py <java_file>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    # Check API key
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        sys.exit(1)
    
    client = Anthropic(api_key=api_key)
    
    print("ENHANCED DOCUMENTATION GENERATOR")
    print("Using BASE-PROMPT.md template with Claude Opus 4.1")
    print("="*60)
    
    # Parse file using tree-sitter
    print(f"\nParsing {file_path} with tree-sitter...")
    items = parse_java_file_simple(file_path)
    
    print(f"Found {len(items)} items to potentially document")
    
    # Process items (same as original)
    for item in items[:3]:  # Process first 3 for testing as in original
        javadoc, impl_notes = generate_documentation_with_diagnostics(client, item)
        
        print(f"\n8. FINAL RESULT FOR {item['name']}:")
        print(f"   JavaDoc generated: {javadoc is not None}")
        print(f"   Impl notes generated: {impl_notes is not None}")
        
        if not impl_notes and item['type'] in ['method', 'constructor']:
            print("\n⚠️  PROBLEM: Implementation notes were NOT generated!")
            print("   This is why your file has no implementation notes.")
    
    print("\n" + "="*60)
    print("DIAGNOSTIC COMPLETE")
    print("="*60)
    print("\nKey improvements in this version:")
    print("1. ✅ Using your BASE-PROMPT.md template properly")
    print("2. ✅ Full implementation code (no [:500] truncation)")
    print("3. ✅ Full file context passed for better understanding")
    print("4. ✅ Using Claude Opus 4.1 for best quality")
    print("5. ✅ Using tree-sitter parser from javadoc_common")


if __name__ == "__main__":
    main()
