#!/usr/bin/env python3

import os
import sys
import subprocess
import traceback
from anthropic import Anthropic

# Import common functionality
from javadoc_common import (
    load_prompt_template,
    parse_java_file,
    extract_javadoc_from_response,
    add_javadoc_to_file
)

# API Configuration
CLAUDE_MODEL = "claude-opus-4-1-20250805"
MAX_TOKENS = 5000
INPUT_TOKEN_COST = 0.000015   # Cost per input token in USD
OUTPUT_TOKEN_COST = 0.000075  # Cost per output token in USD

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

def generate_javadoc(client, item, java_content, prompt_template=None):
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
    if item.get('existing_javadoc'):
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
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
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
            'estimated_cost': (response.usage.input_tokens * INPUT_TOKEN_COST) + (response.usage.output_tokens * OUTPUT_TOKEN_COST)
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

def setup_environment(single_file):
    """Setup environment and validate configuration.

    Returns:
        dict: Configuration with java_files, commit_after, and api_key
    """
    # Determine mode and get files
    if single_file:
        if not os.path.exists(single_file):
            print(f"Error: File {single_file} does not exist", file=sys.stderr)
            sys.exit(1)
        java_files = [single_file]
        commit_after = False
    else:
        java_files = get_changed_java_files()
        commit_after = True

    # Get API key
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)

    return {
        'java_files': java_files,
        'commit_after': commit_after,
        'api_key': api_key
    }

def initialize_usage_stats(client):
    """Initialize usage tracking statistics.

    Returns:
        dict: Usage statistics dictionary
    """
    stats = {
        'total_input_tokens': 0,
        'total_output_tokens': 0,
        'total_tokens': 0,
        'total_cost': 0.0,
        'items_processed': 0,
        'credits_info': None
    }

    initial_credits = get_credits_info(client)
    if initial_credits:
        stats['credits_info'] = initial_credits

    return stats

def read_java_file(file_path):
    """Read a Java file and return its content.

    Args:
        file_path: Path to the Java file

    Returns:
        str: File content

    Raises:
        Exception: If file cannot be read
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def write_updated_file(file_path, java_content, items_with_javadoc):
    """Write updated content back to file.

    Args:
        file_path: Path to the Java file
        java_content: Original Java content
        items_with_javadoc: List of items with generated Javadoc
    """
    updated_content = add_javadoc_to_file(java_content, items_with_javadoc)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)

    print(f"✅ Updated {file_path} with {len(items_with_javadoc)} Javadoc comments")

def print_items_summary(items_needing_docs):
    """Print summary of items found needing documentation.

    Args:
        items_needing_docs: List of items needing documentation
    """
    print(f"Found {len(items_needing_docs)} items needing documentation:")
    for item in items_needing_docs:
        existing = "✔" if item.get('existing_javadoc') else "✗"
        print(f"  - {item['type']}: {item['name']} (existing: {existing})")

def generate_javadoc_for_item(item, java_content, client, prompt_template):
    """Generate Javadoc for a single item.

    Args:
        item: Item dictionary
        java_content: Full Java file content
        client: Anthropic client
        prompt_template: Prompt template string

    Returns:
        tuple: (doc_content, usage_info) or (None, None) on failure
    """
    print(f"\nGenerating Javadoc for {item['type']}: {item['name']}...")
    return generate_javadoc(client, item, java_content, prompt_template)

def update_usage_stats(total_usage_stats, usage_info):
    """Update total usage statistics with new usage info.

    Args:
        total_usage_stats: Dictionary of total usage stats
        usage_info: Dictionary of current usage info
    """
    total_usage_stats['total_input_tokens'] += usage_info['input_tokens']
    total_usage_stats['total_output_tokens'] += usage_info['output_tokens']
    total_usage_stats['total_tokens'] += usage_info['total_tokens']
    total_usage_stats['total_cost'] += usage_info['estimated_cost']
    total_usage_stats['items_processed'] += 1

def print_generation_result(item_name, doc_content, usage_info):
    """Print the result of Javadoc generation.

    Args:
        item_name: Name of the item
        doc_content: Generated documentation content
        usage_info: Usage information dictionary
    """
    has_impl_notes = doc_content.get('implementation_notes') if isinstance(doc_content, dict) else False
    impl_status = " (with implementation notes)" if has_impl_notes else ""
    print(f"✅ Generated{impl_status} ({usage_info['total_tokens']} tokens, ${usage_info['estimated_cost']:.4f})")

def generate_all_javadocs(items_needing_docs, java_content, client, prompt_template, total_usage_stats):
    """Generate Javadoc for all items and update usage stats.

    Args:
        items_needing_docs: List of items needing documentation
        java_content: Full Java file content
        client: Anthropic client
        prompt_template: Prompt template string
        total_usage_stats: Dictionary of total usage stats

    Returns:
        list: Items with generated Javadoc
    """
    items_with_javadoc = []

    for item in items_needing_docs:
        doc_content, usage_info = generate_javadoc_for_item(item, java_content, client, prompt_template)

        if doc_content and usage_info:
            item['javadoc'] = doc_content
            items_with_javadoc.append(item)
            update_usage_stats(total_usage_stats, usage_info)
            print_generation_result(item['name'], doc_content, usage_info)
        else:
            print(f"❌ Failed to generate Javadoc for {item['name']}")

    return items_with_javadoc

def process_single_java_file(java_file, client, prompt_template, total_usage_stats):
    """Process a single Java file and return whether it was modified.

    Args:
        java_file: Path to Java file
        client: Anthropic client
        prompt_template: Prompt template string
        total_usage_stats: Dictionary of total usage stats

    Returns:
        bool: True if file was modified, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"Processing: {java_file}")
    print('='*60)

    try:
        java_content = read_java_file(java_file)
        items_needing_docs = parse_java_file(java_content)

        if not items_needing_docs:
            print(f"No items needing documentation found in {java_file}")
            return False

        print_items_summary(items_needing_docs)
        items_with_javadoc = generate_all_javadocs(items_needing_docs, java_content, client, prompt_template, total_usage_stats)

        if items_with_javadoc:
            write_updated_file(java_file, java_content, items_with_javadoc)
            return True

        return False

    except Exception as e:
        print(f"Error processing {java_file}: {e}\n{traceback.format_exc()}", file=sys.stderr)
        return False

def process_all_files(java_files, client, prompt_template, total_usage_stats):
    """Process all Java files and return list of modified files.

    Args:
        java_files: List of Java file paths
        client: Anthropic client
        prompt_template: Prompt template string
        total_usage_stats: Dictionary of total usage stats

    Returns:
        list: List of modified file paths
    """
    files_modified = []

    for java_file in java_files:
        if process_single_java_file(java_file, client, prompt_template, total_usage_stats):
            files_modified.append(java_file)

    return files_modified

def print_final_summary(java_files, files_modified, total_usage_stats, commit_after):
    """Print final summary of processing.

    Args:
        java_files: List of all Java files processed
        files_modified: List of modified files
        total_usage_stats: Dictionary of total usage stats
        commit_after: Whether files will be committed
    """
    print(f"\n{'='*60}")
    print("SUMMARY")
    print('='*60)
    print(f"Files processed: {len(java_files)}")
    print(f"Files modified: {len(files_modified)}")
    print(f"Items documented: {total_usage_stats['items_processed']}")
    print(f"Total tokens used: {total_usage_stats['total_tokens']}")
    print(f"Estimated cost: ${total_usage_stats['total_cost']:.4f}")

    if not files_modified:
        print("No files were modified.")
        return

    if commit_after:
        commit_changes(files_modified, total_usage_stats)
    else:
        print(f"\n✅ Successfully modified {len(files_modified)} file(s) in debug mode (no commit)")

def main(single_file=None):
    """Main entry point.

    Args:
        single_file: Path to a single Java file to process (for debug mode).
                    If None, runs in GitHub Action mode.
    """
    config = setup_environment(single_file)

    if not config['java_files']:
        print("No Java files found in PR changes.")
        return

    client = Anthropic(api_key=config['api_key'])
    prompt_template = load_prompt_template()
    total_usage_stats = initialize_usage_stats(client)

    files_modified = process_all_files(config['java_files'], client, prompt_template, total_usage_stats)

    print_final_summary(config['java_files'], files_modified, total_usage_stats, config['commit_after'])

if __name__ == "__main__":
    single_file = sys.argv[1] if len(sys.argv) > 1 else None
    main(single_file=single_file)
