#!/usr/bin/env python3

import os
import sys
import subprocess
import traceback
import re
from datetime import datetime
from anthropic import Anthropic

# Import common functionality
from javadoc_common import (
    load_prompt_template,
    parse_java_file,
    extract_javadoc_from_response,
    add_javadoc_to_file
)

def get_current_git_hash():
    """Get the current git commit hash (short version)."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"

def extract_metadata_from_implementation_comment(comment_text):
    """
    Extract metadata (commit hash) from an existing AI Implementation comment.
    
    Returns:
        dict with 'commit_hash' and 'timestamp' if found, None otherwise
    """
    if not comment_text:
        return None
    
    # Look for pattern: // Comments AI generated: TIMESTAMP | Commit: HASH
    pattern = r'//\s*Comments?\s+AI\s+generated:\s*([^\|]+)\s*\|\s*Commit:\s*([a-f0-9]+)'
    match = re.search(pattern, comment_text)
    
    if match:
        return {
            'timestamp': match.group(1).strip(),
            'commit_hash': match.group(2).strip()
        }
    
    return None

def is_meaningful_change(line):
    """
    Determine if a line change is meaningful (not just whitespace or comments).
    
    Args:
        line: A line from git diff (without +/- prefix)
        
    Returns:
        bool: True if this is a meaningful code change
    """
    # Remove the line content (everything after +/- prefix was already removed)
    stripped = line.strip()
    
    # Empty line or whitespace only
    if not stripped:
        return False
    
    # Single-line comment
    if stripped.startswith('//'):
        return False
    
    # Javadoc or multi-line comment start/end
    if stripped.startswith('/*') or stripped.startswith('*') or stripped.startswith('*/'):
        return False
    
    # Check if the line is ONLY opening/closing braces (formatting change)
    if stripped in ['{', '}', '{}', '};', '{', '},']:
        return False
    
    return True

def get_meaningful_code_changes(file_path, start_line, end_line, since_commit):
    """
    Get the character count of meaningful code changes (excluding whitespace and comments).
    
    Args:
        file_path: Path to the file
        start_line: Starting line number of the code block
        end_line: Ending line number of the code block  
        since_commit: Git commit hash to compare against
        
    Returns:
        tuple: (total_changes, meaningful_changes, has_meaningful_changes, change_details)
    """
    try:
        # Get the diff for the specific file since the commit
        result = subprocess.run(
            ['git', 'diff', f'{since_commit}..HEAD', '--', file_path],
            capture_output=True,
            text=True,
            check=True
        )
        
        if not result.stdout:
            # No changes in this file
            return 0, 0, False, "No changes in file"
        
        # Parse the diff to find changes in our line range
        lines = result.stdout.split('\n')
        total_chars_changed = 0
        meaningful_chars_changed = 0
        whitespace_only_changes = 0
        comment_only_changes = 0
        in_relevant_hunk = False
        current_line = 0
        in_multiline_comment = False
        
        for line in lines:
            # Check if we're in a hunk header (e.g., @@ -10,7 +10,7 @@)
            hunk_match = re.match(r'@@ -(\d+),?\d* \+(\d+),?\d* @@', line)
            if hunk_match:
                old_start = int(hunk_match.group(1))
                new_start = int(hunk_match.group(2))
                current_line = new_start - 1  # Will be incremented before use
                
                # Check if this hunk affects our line range
                in_relevant_hunk = (new_start <= end_line and new_start >= start_line)
                continue
            
            if in_relevant_hunk:
                if line.startswith('+') and not line.startswith('+++'):
                    # Added line
                    current_line += 1
                    if start_line <= current_line <= end_line:
                        line_content = line[1:]  # Remove the '+' prefix
                        total_chars_changed += len(line_content)
                        
                        # Check if this is a meaningful change
                        if is_meaningful_change(line_content):
                            meaningful_chars_changed += len(line_content.strip())
                        else:
                            # Track what kind of non-meaningful change
                            if line_content.strip().startswith('//'):
                                comment_only_changes += 1
                            elif not line_content.strip():
                                whitespace_only_changes += 1
                                
                elif line.startswith('-') and not line.startswith('---'):
                    # Removed line (don't increment current_line for removed lines)
                    if start_line <= current_line <= end_line:
                        line_content = line[1:]  # Remove the '-' prefix
                        total_chars_changed += len(line_content)
                        
                        # Check if this is a meaningful change
                        if is_meaningful_change(line_content):
                            meaningful_chars_changed += len(line_content.strip())
                        else:
                            # Track what kind of non-meaningful change
                            if line_content.strip().startswith('//'):
                                comment_only_changes += 1
                            elif not line_content.strip():
                                whitespace_only_changes += 1
                                
                elif not line.startswith('\\'):  # Not a "No newline" message
                    current_line += 1
                    
                # Stop checking if we've passed our line range
                if current_line > end_line:
                    in_relevant_hunk = False
        
        # Build detailed change description
        change_details = []
        if meaningful_chars_changed > 0:
            change_details.append(f"{meaningful_chars_changed} chars of code")
        if whitespace_only_changes > 0:
            change_details.append(f"{whitespace_only_changes} whitespace-only lines")
        if comment_only_changes > 0:
            change_details.append(f"{comment_only_changes} comment-only lines")
        
        if not change_details:
            change_details_str = "No changes"
        else:
            change_details_str = "Changes: " + ", ".join(change_details)
        
        has_meaningful_changes = meaningful_chars_changed > 0
        return total_chars_changed, meaningful_chars_changed, has_meaningful_changes, change_details_str
        
    except subprocess.CalledProcessError as e:
        # If there's an error (e.g., commit not found), assume regeneration is needed
        print(f"Warning: Could not get diff for {file_path} since {since_commit}: {e}")
        return 0, 0, True, "Could not analyze changes (diff failed)"

def should_regenerate_documentation(item, file_path, change_threshold=3):
    """
    Determine if documentation should be regenerated based on meaningful code changes.
    
    Args:
        item: The parsed Java item dict
        file_path: Path to the Java file
        change_threshold: Minimum meaningful character changes to trigger regeneration
        
    Returns:
        tuple: (should_regenerate, reason)
    """
    # Check if there's existing AI Implementation comment with metadata
    existing_impl = item.get('existing_implementation_comment')
    if not existing_impl:
        return True, "No existing implementation comment"
    
    # Extract metadata from the comment
    metadata = extract_metadata_from_implementation_comment(existing_impl)
    if not metadata:
        return True, "No metadata found in existing comment"
    
    previous_commit = metadata['commit_hash']
    
    # Check if we're at the same commit (no changes at all)
    current_commit = get_current_git_hash()
    if previous_commit == current_commit:
        return False, f"No changes since last generation (commit: {previous_commit})"
    
    # Get the line range for this item
    start_line = item.get('start_line', 0)
    end_line = item.get('end_line', 0)
    
    if start_line == 0 or end_line == 0:
        # Can't determine line range, regenerate to be safe
        return True, "Cannot determine code boundaries"
    
    # Check the actual code changes (filtering out non-meaningful changes)
    total_changes, meaningful_changes, has_meaningful_changes, change_details = get_meaningful_code_changes(
        file_path, start_line, end_line, previous_commit
    )
    
    if not has_meaningful_changes:
        if total_changes > 0:
            return False, f"Only whitespace/comment changes since {previous_commit} ({change_details})"
        else:
            return False, f"No changes in code block since {previous_commit}"
    
    if meaningful_changes > change_threshold:
        return True, f"Meaningful code changes: {meaningful_changes} chars (>{change_threshold}) since {previous_commit}. {change_details}"
    else:
        return False, f"Minor code changes: {meaningful_changes} chars (≤{change_threshold}) since {previous_commit}. {change_details}"

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

def add_metadata_to_implementation_notes(implementation_notes, git_hash):
    """
    Add metadata (timestamp and git hash) to implementation notes.
    
    Args:
        implementation_notes: The AI implementation comment content
        git_hash: Current git commit hash
        
    Returns:
        Modified implementation notes with metadata
    """
    if not implementation_notes:
        return implementation_notes
    
    # Get current timestamp in ISO format
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # Add metadata line at the end of the implementation notes
    metadata_line = f"// Comments AI generated: {timestamp} | Commit: {git_hash}"
    
    # If implementation_notes already contains multiple lines, add metadata as a new line
    if '\n' in implementation_notes:
        return f"{implementation_notes}\n{metadata_line}"
    else:
        # For single line comments, add on the next line
        return f"{implementation_notes}\n{metadata_line}"

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
            
            if total_usage_stats.get('items_skipped', 0) > 0:
                commit_msg_parts.append(
                    f"Items skipped (no significant changes): {total_usage_stats['items_skipped']}"
                )
        
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

def generate_javadoc(client, item, java_content, prompt_template=None, regenerate_all=False, git_hash=None):
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
        
        # Add metadata to implementation notes if present
        if extracted_content and isinstance(extracted_content, dict) and extracted_content.get('implementation_notes'):
            extracted_content['implementation_notes'] = add_metadata_to_implementation_notes(
                extracted_content['implementation_notes'],
                git_hash or get_current_git_hash()
            )
        
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
    
    # Get the current git hash once at the beginning
    current_git_hash = get_current_git_hash()
    print(f"Current git commit: {current_git_hash}")
    
    # Determine mode and regeneration setting
    regenerate_all = False
    smart_regeneration = False  # New flag for smart regeneration mode
    
    if single_file:
        # Single file debug mode
        java_files = [single_file]
        commit_after = False
        
        # Check for --smart flag
        if '--smart' in sys.argv:
            smart_regeneration = True
            regenerate_all = False
            print("🧠 Running in SMART REGENERATION mode - only regenerating docs with meaningful code changes")
        else:
            regenerate_all = True
            print("🔄 Running in REGENERATE ALL mode - all existing documentation will be replaced")
        
        # Check if file exists
        if not os.path.exists(single_file):
            print(f"Error: File {single_file} does not exist", file=sys.stderr)
            sys.exit(1)
            
    else:
        # GitHub Action mode - use smart regeneration
        java_files = get_changed_java_files()
        commit_after = True
        regenerate_all = False
        smart_regeneration = True  # Enable smart mode in GitHub Actions
        
        if not java_files:
            print("No Java files found in PR changes.")
            return
        
        print("🧠 Smart regeneration enabled - checking for meaningful code changes")
   
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
        'items_skipped': 0,
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
                # Normal/Smart mode - parse to find what needs work
                items_needing_docs = parse_java_file(original_java_content)
                java_content_for_generation = original_java_content
            
            if not items_needing_docs and not smart_regeneration:
                print(f"No items needing documentation found in {java_file}")
                continue
            
            # In smart regeneration mode, check each item for meaningful changes
            if smart_regeneration and not regenerate_all:
                items_to_process = []
                for item in items_needing_docs:
                    should_regen, reason = should_regenerate_documentation(item, java_file)
                    
                    if should_regen:
                        print(f"  ✅ {item['type']}: {item['name']} - {reason}")
                        items_to_process.append(item)
                    else:
                        print(f"  ⏭️  {item['type']}: {item['name']} - SKIPPED: {reason}")
                        total_usage_stats['items_skipped'] += 1
                
                items_needing_docs = items_to_process
                
                if not items_needing_docs:
                    print(f"No items need regeneration in {java_file} (all changes were trivial)")
                    continue
            else:
                action_word = "regenerate" if regenerate_all else "document"
                print(f"Found {len(items_needing_docs)} items to {action_word}:")
                for item in items_needing_docs:
                    print(f"  - {item['type']}: {item['name']}")
            
            if regenerate_all and items_regenerated > 0:
                print(f"  (Note: Regenerating documentation for all {len(items_needing_docs)} items)")
            
            # Generate Javadoc for each item
            items_with_javadoc = []
            for item in items_needing_docs:
                action = "Regenerating" if (regenerate_all or smart_regeneration) else "Generating"
                print(f"\n{action} Javadoc for {item['type']}: {item['name']}...")
                
                # generate_javadoc now returns a dict with javadoc and implementation_notes
                doc_content, usage_info = generate_javadoc(
                    client, 
                    item, 
                    java_content_for_generation,  # Use original content for context
                    prompt_template,
                    regenerate_all=regenerate_all,
                    git_hash=current_git_hash
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
                    
                    if regenerate_all or smart_regeneration:
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
                action = "regenerated" if (regenerate_all or smart_regeneration) else "added/updated"
                print(f"✅ Updated {java_file} with {len(items_with_javadoc)} {action} Javadoc comments")
            
        except Exception as e:
            print(f"Error processing {java_file}: {e}\n{traceback.format_exc()}", file=sys.stderr)
            continue
    
    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print('='*60)
    if regenerate_all:
        mode_desc = "🔄 REGENERATE ALL"
    elif smart_regeneration:
        mode_desc = "🧠 SMART REGENERATION"
    else:
        mode_desc = "📝 Normal (update missing/improve existing)"
    
    print(f"Mode: {mode_desc}")
    print(f"Files processed: {len(java_files)}")
    print(f"Files modified: {len(files_modified)}")
    print(f"Items documented: {total_usage_stats['items_processed']}")
    if smart_regeneration and total_usage_stats['items_skipped'] > 0:
        print(f"Items skipped (trivial changes): {total_usage_stats['items_skipped']}")
    if regenerate_all and total_usage_stats['items_regenerated'] > 0:
        print(f"Items regenerated: {total_usage_stats['items_regenerated']}")
    print(f"Total tokens used: {total_usage_stats['total_tokens']}")
    print(f"Estimated cost: ${total_usage_stats['total_cost']:.4f}")
    
    if smart_regeneration and total_usage_stats['items_skipped'] > 0:
        savings = total_usage_stats['items_skipped'] * 0.05  # Rough estimate of cost per item
        print(f"💰 Estimated savings from smart skipping: ~${savings:.2f}")
    
    # Commit changes if any files were modified
    if files_modified and commit_after:
        commit_changes(files_modified, total_usage_stats)
    elif not commit_after and files_modified:
        mode_desc = "with full regeneration" if regenerate_all else "with smart regeneration" if smart_regeneration else ""
        print(f"\n✅ Successfully modified {len(files_modified)} file(s) in debug mode {mode_desc} (no commit)")
    elif not files_modified:
        print("No files were modified.")

if __name__ == "__main__":
    # Parse command line arguments
    single_file = None
    for arg in sys.argv[1:]:
        if not arg.startswith('--'):
            single_file = arg
            break
    
    main(single_file=single_file)
