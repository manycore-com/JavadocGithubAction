#!/usr/bin/env python3

import os
import sys
import subprocess
import traceback
import re
from anthropic import Anthropic

# Import common functionality
from javadoc_common import (
    load_prompt_template,
    parse_java_file,
    extract_javadoc_from_response,
    add_javadoc_to_file
)

def get_changed_java_files():
    """Get list of Java files changed in the current PR."""
    try:
        # Get the base branch (usually main or master)
        base_ref = os.environ.get('GITHUB_BASE_REF', 'main')
        
        # Get changed files between base branch and current branch
        result = subprocess.run(
            ['git', 'diff', '--name-only', f'origin/{base_ref}...HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        
        changed_files = result.stdout.strip().split('\n')
        java_files = [f for f in changed_files if f.endswith('.java') and os.path.exists(f)]
        
        print(f"Found {len(java_files)} changed Java files:")
        for f in java_files:
            print(f"  - {f}")
        
        return java_files
    
    except subprocess.CalledProcessError as e:
        print(f"Error getting changed files: {e}", file=sys.stderr)
        return []

def strip_javadoc_and_ai_comments(java_content):
    """
    Remove all Javadoc comments and AI implementation comments from Java content.
    This is used in regenerate mode to force regeneration of all documentation.
    """
    # Remove Javadoc comments (/** ... */)
    # This regex handles multi-line javadoc comments
    java_content = re.sub(r'/\*\*.*?\*/', '', java_content, flags=re.DOTALL)
    
    # Remove AI implementation comments (// AI Implementation: ...)
    # These are typically single-line comments starting with "// AI Implementation:"
    java_content = re.sub(r'//\s*AI\s+Implementation:.*?(?=\n)', '', java_content, flags=re.IGNORECASE)
    
    # Also remove any standalone AI implementation block comments if they exist
    java_content = re.sub(r'/\*\s*AI\s+Implementation:.*?\*/', '', java_content, flags=re.DOTALL | re.IGNORECASE)
    
    # Clean up any excessive blank lines left behind (more than 2 consecutive)
    java_content = re.sub(r'\n{3,}', '\n\n', java_content)
    
    return java_content

def commit_changes(files_modified, total_usage_stats=None):
    """Commit the changes made to Java files with cost information."""
    if not files_modified:
        print("No files were modified.")
        return
    
    try:
        # Add the modified files
        for file_path in files_modified:
            subprocess.run(['git', 'add', file_path], check=True)
        
        # Create commit message
        commit_msg_parts = [
            f"Add/update Javadoc comments for {len(files_modified)} file(s)",
            "",
            "Files modified:"
        ]
        
        for file_path in files_modified:
            commit_msg_parts.append(f"- {file_path}")
        
        if total_usage_stats:
            commit_msg_parts.extend([
                "",
                f"API Usage: {total_usage_stats.get('total_tokens', 0)} tokens, "
                f"${total_usage_stats.get('total_cost', 0):.4f} estimated cost"
            ])
        
        commit_msg_parts.extend([
            "",
            "🤖 Generated with [Claude Code](https://claude.ai/code)",
            "",
            "Co-Authored-By: Claude <noreply@anthropic.com>"
        ])
        
        commit_message = '\n'.join(commit_msg_parts)
        
        # Commit the changes
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)
        print(f"✅ Committed changes for {len(files_modified)} files")
        
    except subprocess.CalledProcessError as e:
        print(f"Error committing changes: {e}", file=sys.stderr)

def generate_javadoc(client, item, java_content, prompt_template=None, regenerate_all=False):
    """Generate Javadoc comment and implementation notes using Claude API."""
    if prompt_template is None:
        prompt_template = load_prompt_template()

    # Prepare template variables
    modifiers = ' '.join(item.get('modifiers', [])) if item.get('modifiers') else 'default'
    parameters = ''
    if item.get('parameters'):
        param_list = []
        for param in item['parameters']:
            param_list.append(f"{param['type']} {param['name']}")
        parameters = ', '.join(param_list)

    # Prepare existing content
    existing_content = ""
    # In regenerate_all mode, we don't pass existing content to get fresh documentation
    if not regenerate_all and item.get('existing_javadoc'):
        existing_javadoc_content = item['existing_javadoc']['content']
        existing_content = f"EXISTING JAVADOC TO PRESERVE/IMPROVE:\n{existing_javadoc_content}"

    # Format the prompt
    prompt = prompt_template.format(
        item_type=item['type'],
        item_name=item['name'],
        item_signature=item.get('signature', ''),
        modifiers=modifiers,
        parameters=parameters,
        return_type=item.get('return_type', ''),
        implementation_code=item.get('implementation_code', ''),
        existing_content=existing_content,
        java_content=java_content 
    )

    try:
        response = client.messages.create(
            model="claude-opus-4-1-20250805",
            max_tokens=5000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Extract both Javadoc and implementation notes from the response
        # The function now returns a dict with 'javadoc' and 'implementation_notes'
        extracted_content = extract_javadoc_from_response(response.content[0].text)
        
        # Calculate usage stats
        usage_info = {
            'input_tokens': response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens,
            'total_tokens': response.usage.input_tokens + response.usage.output_tokens,
            'estimated_cost': (response.usage.input_tokens * 0.000015) + (response.usage.output_tokens * 0.000075)
        }
        
        return extracted_content, usage_info
        
    except Exception as e:
        print(f"Error generating Javadoc for {item['name']}: {e}", file=sys.stderr)
        return None, None

def get_credits_info(client):
    """Get current credits information from Anthropic API."""
    try:
        # This is a placeholder - Anthropic doesn't have a public credits API endpoint
        # In a real implementation, you might track usage locally or use other methods
        return {"credits_remaining": "Unknown", "credits_used": "Unknown"}
    except Exception as e:
        print(f"Warning: Could not get credits info: {e}", file=sys.stderr)
        return None

def main(single_file=None):
    """
    Main entry point.
    
    Args:
        single_file: Path to a single Java file to process (for debug mode).
                    If None, runs in GitHub Action mode.
    """
    
    # Determine mode and regeneration setting
    regenerate_all = False
    if single_file:
        # Single file debug mode - regenerate ALL documentation
        java_files = [single_file]
        commit_after = False
        regenerate_all = True  # Force regeneration in command line mode
        
        # Check if file exists
        if not os.path.exists(single_file):
            print(f"Error: File {single_file} does not exist", file=sys.stderr)
            sys.exit(1)
        
        print("🔄 Running in REGENERATE ALL mode - all existing documentation will be replaced")
            
    else:
        # GitHub Action mode - only update missing/improve existing
        java_files = get_changed_java_files()
        commit_after = True
        regenerate_all = False
        
        if not java_files:
            print("No Java files found in PR changes.")
            return
   
    # Get API key from environment
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    # Initialize Claude client
    client = Anthropic(api_key=api_key)
    # Load prompt template once
    prompt_template = load_prompt_template()
    
    # Initialize usage tracking
    total_usage_stats = {
        'total_input_tokens': 0,
        'total_output_tokens': 0,
        'total_tokens': 0,
        'total_cost': 0.0,
        'items_processed': 0,
        'items_regenerated': 0,
        'credits_info': None
    }
    
    # Try to get initial credits info
    initial_credits = get_credits_info(client)
    if initial_credits:
        total_usage_stats['credits_info'] = initial_credits
    
    files_modified = []
    
    # Process each Java file
    for java_file in java_files:
        print(f"\n{'='*60}")
        print(f"Processing: {java_file}")
        print('='*60)
        
        try:
            # Read the Java file
            with open(java_file, 'r', encoding='utf-8') as f:
                original_java_content = f.read()
            
            # Store item counts for tracking regeneration
            items_regenerated = 0
            
            # Parse the file to find items needing documentation
            if regenerate_all:
                print("🗑️  Stripping existing Javadoc and AI implementation comments...")
                # Strip all existing documentation before parsing
                stripped_content = strip_javadoc_and_ai_comments(original_java_content)
                
                # Parse the stripped content to find ALL items (they'll all appear as needing docs now)
                items_needing_docs = parse_java_file(stripped_content)
                
                # Count how many items originally had docs (for reporting)
                original_items = parse_java_file(original_java_content)
                items_regenerated = len(original_items) - len(items_needing_docs)
                
                # Use the original content for context when generating docs
                java_content_for_generation = original_java_content
            else:
                # Normal mode - only items without docs or needing improvement
                items_needing_docs = parse_java_file(original_java_content)
                java_content_for_generation = original_java_content
            
            if not items_needing_docs:
                print(f"No items needing documentation found in {java_file}")
                continue
            
            action_word = "regenerate" if regenerate_all else "document"
            print(f"Found {len(items_needing_docs)} items to {action_word}:")
            for item in items_needing_docs:
                print(f"  - {item['type']}: {item['name']}")
            
            if regenerate_all and items_regenerated > 0:
                print(f"  (Note: Regenerating documentation for all {len(items_needing_docs)} items)")
            
            # Generate Javadoc for each item
            items_with_javadoc = []
            for item in items_needing_docs:
                action = "Regenerating" if regenerate_all else "Generating"
                print(f"\n{action} Javadoc for {item['type']}: {item['name']}...")
                
                # generate_javadoc now returns a dict with javadoc and implementation_notes
                doc_content, usage_info = generate_javadoc(
                    client, 
                    item, 
                    java_content_for_generation,  # Use original content for context
                    prompt_template,
                    regenerate_all=regenerate_all
                )
                
                if doc_content and usage_info:
                    # Store the entire dict (with both javadoc and implementation_notes)
                    item['javadoc'] = doc_content
                    items_with_javadoc.append(item)
                    
                    # Update usage stats
                    total_usage_stats['total_input_tokens'] += usage_info['input_tokens']
                    total_usage_stats['total_output_tokens'] += usage_info['output_tokens']
                    total_usage_stats['total_tokens'] += usage_info['total_tokens']
                    total_usage_stats['total_cost'] += usage_info['estimated_cost']
                    total_usage_stats['items_processed'] += 1
                    
                    if regenerate_all:
                        total_usage_stats['items_regenerated'] += 1
                    
                    # Show if implementation notes were generated
                    has_impl_notes = doc_content.get('implementation_notes') if isinstance(doc_content, dict) else False
                    impl_status = " (with implementation notes)" if has_impl_notes else ""
                    print(f"✅ {action} complete{impl_status} ({usage_info['total_tokens']} tokens, ${usage_info['estimated_cost']:.4f})")
                else:
                    print(f"❌ Failed to generate Javadoc for {item['name']}")
            
            # Add Javadoc to the file content
            if items_with_javadoc:
                # When regenerating, we work with the stripped content
                if regenerate_all:
                    # Add docs to the stripped version
                    updated_content = add_javadoc_to_file(stripped_content, items_with_javadoc)
                else:
                    # Add docs to the original version
                    updated_content = add_javadoc_to_file(original_java_content, items_with_javadoc)
                
                # Write the updated content back to the file
                with open(java_file, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                
                files_modified.append(java_file)
                action = "regenerated" if regenerate_all else "added/updated"
                print(f"✅ Updated {java_file} with {len(items_with_javadoc)} {action} Javadoc comments")
            
        except Exception as e:
            print(f"Error processing {java_file}: {e}\n{traceback.format_exc()}", file=sys.stderr)
            continue
    
    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print('='*60)
    print(f"Mode: {'🔄 REGENERATE ALL' if regenerate_all else '📝 Normal (update missing/improve existing)'}")
    print(f"Files processed: {len(java_files)}")
    print(f"Files modified: {len(files_modified)}")
    print(f"Items documented: {total_usage_stats['items_processed']}")
    if regenerate_all and total_usage_stats['items_regenerated'] > 0:
        print(f"Items regenerated: {total_usage_stats['items_regenerated']}")
    print(f"Total tokens used: {total_usage_stats['total_tokens']}")
    print(f"Estimated cost: ${total_usage_stats['total_cost']:.4f}")
    
    # Commit changes if any files were modified
    if files_modified and commit_after:
        commit_changes(files_modified, total_usage_stats)
    elif not commit_after and files_modified:
        mode_desc = "with full regeneration" if regenerate_all else ""
        print(f"\n✅ Successfully modified {len(files_modified)} file(s) in debug mode {mode_desc} (no commit)")
    elif not files_modified:
        print("No files were modified.")

if __name__ == "__main__":
    single_file = sys.argv[1] if len(sys.argv) > 1 else None
    main(single_file=single_file)
