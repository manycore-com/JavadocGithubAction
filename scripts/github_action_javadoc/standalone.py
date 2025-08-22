#!/usr/bin/env python3

import os
import sys
import argparse
from anthropic import Anthropic

# Import common functionality
from javadoc_common import (
    load_prompt_template,
    parse_java_file,
    extract_javadoc_from_response,
    add_javadoc_to_file
)

def generate_javadoc(client, item):
    """Generate Javadoc using Claude API."""
    prompt_template = load_prompt_template()
    
    # Prepare existing content section
    existing_content = ""
    if item.get('existing_javadoc'):
        existing_content = f"EXISTING JAVADOC TO PRESERVE/IMPROVE:\n{item['existing_javadoc']['content']}"
    
    # Create prompt
    prompt = prompt_template.format(
        item_type=item['type'],
        item_name=item['name'],
        item_signature=item.get('signature', f"{' '.join(item.get('modifiers', []))} {item['name']}"),
        implementation_code=item.get('implementation_code', '// Implementation details not available in standalone mode'),
        existing_content=existing_content
    )
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        javadoc = extract_javadoc_from_response(response.content[0].text)
        return javadoc
        
    except Exception as e:
        print(f"Error generating Javadoc for {item['name']}: {e}", file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(description='Generate Javadoc comments for Java files')
    parser.add_argument('java_file', help='Path to Java file')
    parser.add_argument('--api-key', help='Anthropic API key (or set ANTHROPIC_API_KEY env var)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be generated without making API calls')
    parser.add_argument('--output-only', action='store_true', help='Only print generated Javadoc, do not modify file')
    args = parser.parse_args()

    # Read Java file
    try:
        with open(args.java_file, 'r', encoding='utf-8') as f:
            java_content = f.read()
    except Exception as e:
        print(f"Error reading file {args.java_file}: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse Java file
    items = parse_java_file(java_content)
    if not items:
        print("No public classes or methods found that need documentation.")
        return

    print(f"Found {len(items)} items that need Javadoc:")
    for item in items:
        modifiers = ', '.join(item.get('modifiers', []))
        existing = "Yes" if item.get('existing_javadoc') else "No"
        print(f"- {item['type']}: {item['name']} (modifiers: {modifiers}, existing: {existing})")

    if args.dry_run:
        print("\nDry run mode - no API calls made.")
        return

    # Get API key
    api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: No API key provided. Use --api-key or set ANTHROPIC_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)

    # Initialize Claude client
    client = Anthropic(api_key=api_key)

    print("\nGenerating Javadoc comments...")
    items_with_javadoc = []
    
    for item in items:
        print(f"\nProcessing {item['type']}: {item['name']}")
        
        # Generate Javadoc
        javadoc = generate_javadoc(client, item)
        if javadoc:
            item['javadoc'] = javadoc
            items_with_javadoc.append(item)
            
            if args.output_only:
                print("Generated Javadoc:")
                print(javadoc)
                print("-" * 50)
            else:
                print(f"✅ Generated Javadoc for {item['name']}")
        else:
            print(f"❌ Failed to generate Javadoc for {item['name']}")
    
    # Modify the file if we're not in output-only mode
    if items_with_javadoc and not args.output_only:
        print(f"\nUpdating {args.java_file} with {len(items_with_javadoc)} Javadoc comments...")
        
        try:
            updated_content = add_javadoc_to_file(java_content, items_with_javadoc)
            
            # Write the updated content back to the file
            with open(args.java_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            print(f"✅ Successfully updated {args.java_file}")
            
        except Exception as e:
            print(f"❌ Error updating file: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.output_only:
        print(f"\nOutput-only mode: {args.java_file} was not modified")

if __name__ == "__main__":
    main()