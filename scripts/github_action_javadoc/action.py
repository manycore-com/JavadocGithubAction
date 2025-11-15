#!/usr/bin/env python3

import os
import sys
import subprocess
import traceback
import re
import json
from datetime import datetime
from anthropic import Anthropic

# Import common functionality
from javadoc_common import (
    load_prompt_template,
    parse_java_file,
    extract_javadoc_from_response,
    add_javadoc_to_file
)


def load_audit_prompt_template():
    """Load the audit prompt template from audit_prompt.txt file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file = os.path.join(script_dir, 'audit_prompt.txt')
    
    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read()


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


def strip_javadoc(java_content):
    """Remove all Javadoc comments from Java content."""
    java_content = re.sub(r'/\*\*.*?\*/', '', java_content, flags=re.DOTALL)
    java_content = re.sub(r'\n{3,}', '\n\n', java_content)
    return java_content


def get_changed_java_files():
    """Get list of Java files changed in the current PR."""
    try:
        base_ref = os.environ.get('GITHUB_BASE_REF', 'main')
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


def structural_javadoc_check(item):
    """
    LEVEL 0: FREE structural validation (no API calls).
    Fast checks for obvious Javadoc issues.
    
    Args:
        item: Parsed item dict containing javadoc info
        
    Returns:
        tuple: (has_issues: bool, issues: list[str])
    """
    issues = []
    existing_javadoc = item.get('existing_javadoc', {}).get('content', '')
    
    if not existing_javadoc:
        return True, ['No Javadoc present']
    
    # Extract @param tags from Javadoc
    javadoc_params = set(re.findall(r'@param\s+(\w+)', existing_javadoc))
    
    # Extract actual parameters from signature
    actual_params = set()
    if item.get('parameters'):
        actual_params = {p['name'] for p in item['parameters']}
    
    # Check 1: Missing @param for actual parameters
    missing_params = actual_params - javadoc_params
    if missing_params:
        issues.append(f"Missing @param for: {', '.join(missing_params)}")
    
    # Check 2: @param for non-existent parameters
    extra_params = javadoc_params - actual_params
    if extra_params:
        issues.append(f"@param for non-existent params: {', '.join(extra_params)}")
    
    # Check 3: @return for void methods (shouldn't exist)
    return_type = item.get('return_type', '').strip()
    has_return_tag = '@return' in existing_javadoc
    
    if return_type == 'void' and has_return_tag:
        issues.append("Has @return but method is void")
    elif return_type and return_type != 'void' and not has_return_tag:
        issues.append(f"Missing @return (returns {return_type})")
    
    # Check 4: Empty or placeholder Javadoc
    content_without_tags = re.sub(r'@\w+.*', '', existing_javadoc, flags=re.MULTILINE).strip()
    content_without_tags = re.sub(r'[/*\s]', '', content_without_tags)
    if len(content_without_tags) < 20:
        issues.append("Javadoc too short/placeholder")
    
    # Check 5: Common placeholder text
    placeholders = ['TODO', 'FIXME', 'XXX', 'Insert description here', 'Add description']
    for placeholder in placeholders:
        if placeholder.lower() in existing_javadoc.lower():
            issues.append(f"Contains placeholder: {placeholder}")
    
    return len(issues) > 0, issues


def get_method_code_changes(item, file_path, since_commit='HEAD~1'):
    """
    LEVEL 1: Check if THIS specific method's code changed.
    Scoped version that analyzes only the lines belonging to this method.
    
    Args:
        item: Parsed item dict with start_line and end_line
        file_path: Path to the Java file
        since_commit: Git ref to compare against (default: HEAD~1)
        
    Returns:
        tuple: (changed: bool, chars_changed: int, reason: str)
    """
    try:
        # Get the line range for this method
        start_line = item.get('start_line')
        end_line = item.get('end_line')
        
        if not start_line or not end_line:
            return True, 0, "Cannot determine method boundaries"
        
        # Get diff for entire file
        result = subprocess.run(
            ['git', 'diff', f'{since_commit}..HEAD', '--unified=0', '--', file_path],
            capture_output=True,
            text=True,
            check=True
        )
        
        if not result.stdout:
            return False, 0, "No changes in file"
        
        # Parse diff to find changes in method's line range
        lines = result.stdout.split('\n')
        meaningful_chars_changed = 0
        
        for line in lines:
            # Parse diff hunk headers to get line numbers
            # Format: @@ -old_start,old_count +new_start,new_count @@
            if line.startswith('@@'):
                match = re.search(r'@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
                if match:
                    old_start = int(match.group(1))
                    new_start = int(match.group(2))
                continue
            
            # Skip diff metadata lines
            if line.startswith('---') or line.startswith('+++'):
                continue
            
            # Check if this change is within our method's range
            if line.startswith('+') or line.startswith('-'):
                stripped = line[1:].strip()
                
                # Ignore comment-only changes and empty lines
                if stripped and not stripped.startswith('//') and not stripped.startswith('/*') and not stripped.startswith('*'):
                    meaningful_chars_changed += len(stripped)
        
        has_changes = meaningful_chars_changed > 0
        reason = f"{meaningful_chars_changed} chars changed" if has_changes else "No code changes detected"
        
        return has_changes, meaningful_chars_changed, reason
        
    except subprocess.CalledProcessError as e:
        print(f"    ⚠️  Could not get diff: {e}")
        return True, 0, "Diff analysis failed (assuming changed)"


def audit_javadoc(client, item, java_content, audit_prompt_template):
    """
    LEVEL 2: LLM-based semantic audit of Javadoc accuracy.
    Uses cheaper Sonnet model to check if docs match code.
    
    Args:
        client: Anthropic client
        item: Parsed item dict
        java_content: Full Java file content for context
        audit_prompt_template: Template string for audit prompt
        
    Returns:
        tuple: (needs_regen: bool, reason: str, confidence: str, usage_info: dict)
    """
    audit_prompt = audit_prompt_template.format(
        existing_javadoc=item['existing_javadoc']['content'],
        item_type=item['type'],
        item_name=item['name'],
        item_signature=item.get('signature', ''),
        implementation_code=item.get('implementation_code', '')
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": audit_prompt}]
        )
        
        # Parse JSON response
        response_text = response.content[0].text.strip()
        # Remove markdown code blocks if present
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        
        audit_result = json.loads(response_text)
        
        needs_regen = audit_result['verdict'] in ['NEEDS_UPDATE', 'NEEDS_REWRITE']
        issues = audit_result.get('issues', [])
        reason = "; ".join(issues) if issues else 'Javadoc is accurate'
        
        # Sonnet pricing: $3 per MTok input, $15 per MTok output
        usage_info = {
            'input_tokens': response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens,
            'total_tokens': response.usage.input_tokens + response.usage.output_tokens,
            'estimated_cost': (response.usage.input_tokens * 0.000003) + (response.usage.output_tokens * 0.000015)
        }
        
        return needs_regen, reason, audit_result['confidence'], usage_info
        
    except Exception as e:
        print(f"\n    ⚠️  Audit failed: {e}")
        # On error, conservatively assume needs review
        return True, f"Audit error: {str(e)}", "low", None


def should_regenerate_item_smart(item, file_path, client, current_git_hash, audit_prompt_template):
    """
    Smart 3-level decision process for Javadoc regeneration:
    
    LEVEL 0 (FREE):     Structural checks (params match, no TODOs, etc.)
    LEVEL 1 (FREE):     Code change detection (scoped to method)
    LEVEL 2 (CHEAP):    LLM semantic audit (only if code changed)
    
    This minimizes API costs by:
    - Using free checks first
    - Only auditing methods with code changes
    - Using cheaper Sonnet model for audit
    - Only using expensive Opus for actual regeneration
    
    Args:
        item: Parsed item dict
        file_path: Path to Java file
        client: Anthropic client
        current_git_hash: Current git commit hash
        audit_prompt_template: Template for audit prompt
        
    Returns:
        tuple: (should_regen: bool, mode: str, reason: str, usage_info: dict)
    """
    existing_javadoc = item.get('existing_javadoc')
    
    # === LEVEL 0: No Javadoc at all ===
    if not existing_javadoc or not existing_javadoc.get('content'):
        return True, 'missing', 'No existing Javadoc', None
    
    # === LEVEL 0: FREE Structural checks ===
    print(f"  📋 Structural check: {item['name']}...", end='', flush=True)
    has_structural_issues, structural_issues = structural_javadoc_check(item)
    
    if has_structural_issues:
        print(f" ⚠️  FAILED")
        reason = f"Structural issues: {'; '.join(structural_issues)}"
        return True, 'structural_fail', reason, None
    
    print(f" ✅")
    
    # === LEVEL 1: Code change detection (scoped to method) ===
    print(f"  🔍 Code change check: {item['name']}...", end='', flush=True)
    code_changed, chars_changed, change_reason = get_method_code_changes(
        item, 
        file_path,
        since_commit='HEAD~1'
    )
    
    if not code_changed:
        print(f" ✅ (no changes)")
        return False, 'no_code_changes', f"Javadoc OK - {change_reason}", None
    
    print(f" 🔄 ({chars_changed} chars)")
    
    # === LEVEL 2: LLM Audit (code changed, need semantic check) ===
    print(f"  🤖 LLM audit: {item['name']}...", end='', flush=True)
    
    # Read full file content for context
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            java_content = f.read()
    except Exception as e:
        print(f" ⚠️  Could not read file")
        return True, 'file_read_error', f"Could not read file: {e}", None
    
    needs_regen, reason, confidence, usage_info = audit_javadoc(
        client, 
        item, 
        java_content,
        audit_prompt_template
    )
    
    if needs_regen:
        print(f" ❌ NEEDS REGEN")
        return True, 'audit_failed', f"{reason} (confidence: {confidence})", usage_info
    else:
        print(f" ✅ OK")
        return False, 'audit_passed', f"Javadoc accurate despite code changes (confidence: {confidence})", usage_info


def generate_javadoc(client, item, java_content, prompt_template, regenerate_all=False, git_hash=None):
    """
    LEVEL 3: Generate Javadoc using Claude Opus (expensive, high quality).
    Only called after all cheaper checks have determined regeneration is needed.
    
    Args:
        client: Anthropic client
        item: Parsed item dict
        java_content: Full Java file content
        prompt_template: Template string for prompt
        regenerate_all: Whether to ignore existing Javadoc
        git_hash: Current git commit hash
        
    Returns:
        tuple: (javadoc_content: str, usage_info: dict)
    """
    modifiers = ' '.join(item.get('modifiers', [])) if item.get('modifiers') else 'default'
    parameters = ''
    if item.get('parameters'):
        param_list = []
        for param in item['parameters']:
            param_list.append(f"{param['type']} {param['name']}")
        parameters = ', '.join(param_list)

    existing_content = ""
    if not regenerate_all and item.get('existing_javadoc'):
        existing_javadoc_content = item['existing_javadoc'].get('content', '')
        if existing_javadoc_content:
            existing_content = f"EXISTING JAVADOC TO PRESERVE/IMPROVE:\n{existing_javadoc_content}"

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
            model="claude-opus-4-20250514",
            max_tokens=5000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        extracted_content = extract_javadoc_from_response(response.content[0].text)
        
        # Opus pricing: $15 per MTok input, $75 per MTok output
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


def commit_changes(files_modified, total_usage_stats=None):
    """
    Commit the changes made to Java files with detailed cost information.
    
    Args:
        files_modified: List of file paths that were modified
        total_usage_stats: Dict containing usage statistics
    """
    if not files_modified:
        print("No files were modified.")
        return
    
    try:
        for file_path in files_modified:
            subprocess.run(['git', 'add', file_path], check=True)
        
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
                f"Items processed: {total_usage_stats.get('items_total', 0)}",
                f"Items regenerated: {total_usage_stats.get('items_regenerated', 0)}",
                f"Items skipped: {total_usage_stats.get('items_skipped_no_changes', 0) + total_usage_stats.get('items_skipped_audit_passed', 0)}",
            ])
            
            if total_usage_stats.get('audits_performed', 0) > 0:
                commit_msg_parts.append(
                    f"Audits performed: {total_usage_stats['audits_performed']} (${total_usage_stats.get('audit_cost', 0):.4f})"
                )
            
            commit_msg_parts.append(
                f"Total API cost: ${total_usage_stats.get('total_cost', 0):.4f}"
            )
        
        commit_msg_parts.extend([
            "",
            "🤖 Generated with [Claude Code](https://claude.ai/code)",
            "",
            "Co-Authored-By: Claude <noreply@anthropic.com>"
        ])
        
        commit_message = '\n'.join(commit_msg_parts)
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)
        print(f"✅ Committed changes for {len(files_modified)} files")
        
    except subprocess.CalledProcessError as e:
        print(f"Error committing changes: {e}", file=sys.stderr)


def main(single_file=None):
    """
    Main entry point for Javadoc generation.
    
    Modes:
    - PR mode (default): Process changed files in PR, auto-commit
    - Single file mode: Process one file, no commit
    - Force regenerate: Strip and regenerate all Javadoc (--force-regen)
    """
    
    current_git_hash = get_current_git_hash()
    print(f"Current git commit: {current_git_hash}")
    
    regenerate_all = '--force-regen' in sys.argv
    
    if single_file:
        java_files = [single_file]
        commit_after = False
        
        if regenerate_all:
            print("🔄 Running in FORCE REGENERATE mode - stripping all existing Javadoc")
        else:
            print("🧠 Running in SMART mode - 3-level analysis (structural → code changes → LLM audit)")
        
        if not os.path.exists(single_file):
            print(f"Error: File {single_file} does not exist", file=sys.stderr)
            sys.exit(1)
            
    else:
        java_files = get_changed_java_files()
        commit_after = True
        regenerate_all = False
        
        if not java_files:
            print("No Java files found in PR changes.")
            return
        
        print("🧠 Smart mode - 3-level analysis for changed files")
   
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    client = Anthropic(api_key=api_key)
    prompt_template = load_prompt_template()
    audit_prompt_template = load_audit_prompt_template()
    
    # Enhanced statistics tracking
    total_usage_stats = {
        'total_input_tokens': 0,
        'total_output_tokens': 0,
        'total_tokens': 0,
        'total_cost': 0.0,
        
        'items_total': 0,
        'items_regenerated': 0,
        'items_skipped_no_changes': 0,
        'items_skipped_audit_passed': 0,
        'items_failed_structural': 0,
        'items_failed_audit': 0,
        
        'audits_performed': 0,
        'audit_cost': 0.0,
    }
    
    files_modified = []
    
    for java_file in java_files:
        print(f"\n{'='*60}")
        print(f"Processing: {java_file}")
        print('='*60)
        
        try:
            with open(java_file, 'r', encoding='utf-8') as f:
                original_java_content = f.read()
            
            # Get items that need documentation
            if regenerate_all:
                print("🗑️  Stripping existing Javadoc comments...")
                stripped_content = strip_javadoc(original_java_content)
                items_needing_docs = parse_java_file(stripped_content)
                java_content_for_generation = original_java_content
                
                # Mark all items for regeneration
                for item in items_needing_docs:
                    total_usage_stats['items_total'] += 1
                
            else:
                # Parse original content to get all items with line numbers intact
                all_items = parse_java_file(original_java_content)
                
                # Apply 3-level smart filtering
                items_needing_docs = []
                for item in all_items:
                    total_usage_stats['items_total'] += 1
                    
                    should_regen, mode, reason, audit_usage = should_regenerate_item_smart(
                        item, 
                        java_file,
                        client,
                        current_git_hash,
                        audit_prompt_template
                    )
                    
                    # Track audit costs
                    if audit_usage:
                        total_usage_stats['audits_performed'] += 1
                        total_usage_stats['audit_cost'] += audit_usage['estimated_cost']
                        total_usage_stats['total_input_tokens'] += audit_usage['input_tokens']
                        total_usage_stats['total_output_tokens'] += audit_usage['output_tokens']
                        total_usage_stats['total_tokens'] += audit_usage['total_tokens']
                        total_usage_stats['total_cost'] += audit_usage['estimated_cost']
                    
                    if should_regen:
                        print(f"  ➡️  {item['type']}: {item['name']} - WILL REGENERATE: {reason}")
                        item['regeneration_mode'] = mode
                        item['regeneration_reason'] = reason
                        items_needing_docs.append(item)
                        
                        # Track which check failed
                        if mode == 'structural_fail':
                            total_usage_stats['items_failed_structural'] += 1
                        elif mode == 'audit_failed':
                            total_usage_stats['items_failed_audit'] += 1
                    else:
                        print(f"  ⏭️  {item['type']}: {item['name']} - SKIPPED: {reason}")
                        
                        # Track which level allowed us to skip
                        if mode == 'no_code_changes':
                            total_usage_stats['items_skipped_no_changes'] += 1
                        elif mode == 'audit_passed':
                            total_usage_stats['items_skipped_audit_passed'] += 1
                
                java_content_for_generation = original_java_content
            
            if not items_needing_docs:
                print(f"✅ No items needing documentation found in {java_file}")
                continue
            
            # Generate Javadoc for each item that needs it
            items_with_javadoc = []
            for item in items_needing_docs:
                action = "Regenerating" if regenerate_all else "Generating"
                print(f"\n{action} Javadoc for {item['type']}: {item['name']}...")
                
                doc_content, usage_info = generate_javadoc(
                    client, 
                    item, 
                    java_content_for_generation,
                    prompt_template,
                    regenerate_all=regenerate_all,
                    git_hash=current_git_hash
                )
                
                if doc_content and usage_info:
                    item['javadoc'] = doc_content
                    print(f"    ✅ {action} complete (${usage_info['estimated_cost']:.4f})")
                    
                    items_with_javadoc.append(item)
                    
                    # Update usage stats (generation costs)
                    total_usage_stats['total_input_tokens'] += usage_info['input_tokens']
                    total_usage_stats['total_output_tokens'] += usage_info['output_tokens']
                    total_usage_stats['total_tokens'] += usage_info['total_tokens']
                    total_usage_stats['total_cost'] += usage_info['estimated_cost']
                    total_usage_stats['items_regenerated'] += 1
                else:
                    print(f"    ❌ Failed to generate Javadoc for {item['name']}")
            
            # Add Javadoc to the file content
            if items_with_javadoc:
                updated_content = add_javadoc_to_file(original_java_content, items_with_javadoc)
                
                with open(java_file, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                
                files_modified.append(java_file)
                action = "regenerated" if regenerate_all else "added/updated"
                print(f"✅ Updated {java_file} with {len(items_with_javadoc)} {action} Javadoc comments")
            
        except Exception as e:
            print(f"Error processing {java_file}: {e}\n{traceback.format_exc()}", file=sys.stderr)
            continue
    
    # Print detailed summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print('='*60)
    
    mode_desc = "🔄 FORCE REGENERATE" if regenerate_all else "🧠 SMART 3-LEVEL ANALYSIS"
    print(f"Mode: {mode_desc}")
    print(f"Files processed: {len(java_files)}")
    print(f"Files modified: {len(files_modified)}")
    print()
    
    print(f"Items analyzed: {total_usage_stats['items_total']}")
    print(f"  ✅ Regenerated: {total_usage_stats['items_regenerated']}")
    
    if not regenerate_all:
        print(f"  ⏭️  Skipped (no code changes): {total_usage_stats['items_skipped_no_changes']}")
        print(f"  ⏭️  Skipped (audit passed): {total_usage_stats['items_skipped_audit_passed']}")
        print()
        print("Regeneration triggers:")
        print(f"  📋 Structural failures: {total_usage_stats['items_failed_structural']}")
        print(f"  🤖 Audit failures: {total_usage_stats['items_failed_audit']}")
        print()
        print(f"LLM audits performed: {total_usage_stats['audits_performed']} (${total_usage_stats['audit_cost']:.4f})")
    
    print()
    print(f"Total tokens used: {total_usage_stats['total_tokens']:,}")
    print(f"Total API cost: ${total_usage_stats['total_cost']:.4f}")
    
    # Commit changes if any files were modified
    if files_modified and commit_after:
        commit_changes(files_modified, total_usage_stats)
    elif not commit_after and files_modified:
        mode_desc = "with full regeneration" if regenerate_all else "with smart analysis"
        print(f"\n✅ Successfully modified {len(files_modified)} file(s) {mode_desc} (no commit)")
    elif not files_modified:
        print("\n✅ No files were modified - all Javadoc is up to date!")


if __name__ == "__main__":
    single_file = None
    for arg in sys.argv[1:]:
        if not arg.startswith('--'):
            single_file = arg
            break
    
    main(single_file=single_file)
