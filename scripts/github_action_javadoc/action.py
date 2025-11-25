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
from heuristic_checks import run_heuristic_checks, should_skip_ai_assessment

# API Configuration
CLAUDE_MODEL_OPUS = "claude-opus-4-1-20250805"
CLAUDE_MODEL_HAIKU = "claude-3-5-haiku-20241022"
MAX_TOKENS = 5000
OPUS_INPUT_TOKEN_COST = 0.000015   # Cost per input token in USD for Opus
OPUS_OUTPUT_TOKEN_COST = 0.000075  # Cost per output token in USD for Opus
HAIKU_INPUT_TOKEN_COST = 0.000001  # Cost per input token in USD for Haiku
HAIKU_OUTPUT_TOKEN_COST = 0.000005 # Cost per output token in USD for Haiku

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
    """Generate Javadoc comment using Claude API."""
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
            model=CLAUDE_MODEL_OPUS,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract Javadoc from the response
        extracted_content = extract_javadoc_from_response(response.content[0].text)

        # Calculate usage stats
        usage_info = {
            'input_tokens': response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens,
            'total_tokens': response.usage.input_tokens + response.usage.output_tokens,
            'estimated_cost': (response.usage.input_tokens * OPUS_INPUT_TOKEN_COST) + (response.usage.output_tokens * OPUS_OUTPUT_TOKEN_COST)
        }
        
        return extracted_content, usage_info
        
    except Exception as e:
        print(f"Error generating Javadoc for {item['name']}: {e}", file=sys.stderr)
        return None, None

def load_assessment_prompt():
    """Load the assessment prompt template from ASSESSMENT-PROMPT.md.

    Returns:
        str: Assessment prompt template or None if not found
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    assessment_prompt_path = os.path.join(script_dir, 'ASSESSMENT-PROMPT.md')

    if os.path.exists(assessment_prompt_path):
        try:
            with open(assessment_prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Warning: Failed to load ASSESSMENT-PROMPT.md: {e}", file=sys.stderr)

    # Fallback to hardcoded prompt if file not found
    return """You are assessing the quality of a Javadoc comment for a Java {item_type}.

ITEM DETAILS:
Name: {item_name}
Signature: {item_signature}

EXISTING JAVADOC:
{existing_javadoc}

IMPLEMENTATION CODE:
{implementation_code}

Assess whether this Javadoc needs improvement. Consider:
1. Is it accurate and complete?
2. Does it properly document all parameters with @param tags?
3. Does it properly document the return value with @return tag (for non-void methods)?
4. Does it document exceptions with @throws tags?
5. Is it clear and helpful?
6. Does it match what the code actually does?

Respond with ONLY one word:
- "GOOD" if the Javadoc is adequate and doesn't need improvement
- "IMPROVE" if the Javadoc needs to be regenerated
"""


def assess_javadoc_quality(client, item, existing_javadoc):
    """Assess the quality of existing Javadoc using Haiku.

    Returns True if the Javadoc needs improvement, False otherwise.
    """
    # Load assessment prompt template
    prompt_template = load_assessment_prompt()

    # Format the prompt with item details
    assessment_prompt = prompt_template.format(
        item_type=item['type'],
        item_name=item['name'],
        item_signature=item.get('signature', ''),
        modifiers=item.get('modifiers', ''),
        existing_javadoc=existing_javadoc,
        implementation_code=item.get('implementation_code', '')
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL_HAIKU,
            max_tokens=10,
            messages=[{"role": "user", "content": assessment_prompt}]
        )

        assessment = response.content[0].text.strip().upper()

        # Calculate usage stats for tracking
        usage_info = {
            'input_tokens': response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens,
            'total_tokens': response.usage.input_tokens + response.usage.output_tokens,
            'estimated_cost': (response.usage.input_tokens * HAIKU_INPUT_TOKEN_COST) + (response.usage.output_tokens * HAIKU_OUTPUT_TOKEN_COST)
        }

        needs_improvement = "IMPROVE" in assessment
        return needs_improvement, usage_info

    except Exception as e:
        print(f"Error assessing Javadoc quality for {item['name']}: {e}", file=sys.stderr)
        # On error, default to not needing improvement to avoid unnecessary regeneration
        return False, None

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
        'items_bypassed_by_heuristics': 0,
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

def process_item_with_pipeline(item, java_content, client, prompt_template, total_usage_stats, file_path):
    """Process a single item through the 3-stage quality assessment pipeline.

    Stage 1: Heuristic checks (free, fast)
    Stage 2: Haiku assessment (only if heuristics fail)
    Stage 3: Opus generation (only if Haiku says IMPROVE)

    For items without existing Javadoc: generate 1 version with Opus
    For items with existing Javadoc: run through 3-stage pipeline

    Args:
        item: Item dictionary
        java_content: Full Java file content
        client: Anthropic client
        prompt_template: Prompt template string
        total_usage_stats: Dictionary of total usage stats to update
        file_path: Path to the Java source file (for git diff checks)

    Returns:
        dict: Result dictionary with 'javadoc', 'alternatives', and 'used_existing' keys
    """
    existing_javadoc = item.get('existing_javadoc')

    # Case 1: No existing Javadoc - generate 1 version
    if not existing_javadoc:
        print(f"\nGenerating Javadoc for {item['type']}: {item['name']} (no existing javadoc)...")
        doc_content, usage_info = generate_javadoc(client, item, java_content, prompt_template)
        if doc_content and usage_info:
            update_usage_stats(total_usage_stats, usage_info)
            print(f"✅ Generated ({usage_info['total_tokens']} tokens, ${usage_info['estimated_cost']:.4f})")
            return {
                'javadoc': doc_content,
                'alternatives': None,
                'used_existing': False
            }
        return None

    # Case 2: Has existing Javadoc - run through 3-stage pipeline
    print(f"\nProcessing existing Javadoc for {item['type']}: {item['name']}...")

    # STAGE 1: Heuristic checks (free, fast)
    print(f"  Stage 1: Running heuristic checks...")
    heuristic_result = run_heuristic_checks(
        item=item,
        existing_javadoc=existing_javadoc['content'],
        file_path=file_path,
        strict_mode=True
    )

    # If heuristics pass, trust them and skip AI assessment (cost optimization)
    if should_skip_ai_assessment(heuristic_result):
        print(f"  ✅ Heuristics PASS - keeping existing Javadoc (bypassed AI assessment)")
        total_usage_stats['items_bypassed_by_heuristics'] += 1
        return {
            'javadoc': existing_javadoc['content'],
            'alternatives': None,
            'used_existing': True
        }

    # Heuristics failed - report reasons and proceed to AI assessment
    print(f"  ⚠️  Heuristics FAIL - issues found:")
    for reason in heuristic_result.reasons:
        print(f"      - {reason}")

    # STAGE 2: Haiku assessment (only if heuristics failed)
    print(f"  Stage 2: Running Haiku quality assessment...")
    needs_improvement, assessment_usage = assess_javadoc_quality(
        client, item, existing_javadoc['content']
    )

    if assessment_usage:
        update_usage_stats(total_usage_stats, assessment_usage)
        print(f"  Assessment: {'IMPROVE' if needs_improvement else 'GOOD'} "
              f"({assessment_usage['total_tokens']} tokens, ${assessment_usage['estimated_cost']:.4f})")

    # If Haiku says it's good despite heuristic warnings, keep existing
    if not needs_improvement:
        print(f"✅ Haiku overrides heuristics - keeping existing Javadoc")
        return {
            'javadoc': existing_javadoc['content'],
            'alternatives': None,
            'used_existing': True
        }

    # STAGE 3: Opus generation - generate 2 versions + keep original (3 total)
    print(f"  Stage 3: Generating 2 alternative versions with Opus...")

    versions = []
    for i in range(2):
        print(f"    Generating version {i+1}...")
        doc_content, usage_info = generate_javadoc(client, item, java_content, prompt_template)
        if doc_content and usage_info:
            versions.append(doc_content)
            update_usage_stats(total_usage_stats, usage_info)
            print(f"    ✅ Version {i+1} generated ({usage_info['total_tokens']} tokens, ${usage_info['estimated_cost']:.4f})")
        else:
            print(f"    ❌ Failed to generate version {i+1}")

    if len(versions) == 0:
        print(f"❌ Failed to generate any versions")
        return None

    # Use first version as primary, store both alternatives (version 2 + original)
    alternatives = []
    if len(versions) > 1:
        alternatives.append({
            'label': 'Alternative 1',
            'content': versions[1]
        })
    alternatives.append({
        'label': 'Original',
        'content': existing_javadoc['content']
    })

    return {
        'javadoc': versions[0],
        'alternatives': alternatives,
        'used_existing': False
    }

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
    print(f"✅ Generated ({usage_info['total_tokens']} tokens, ${usage_info['estimated_cost']:.4f})")

def generate_all_javadocs(items_needing_docs, java_content, file_path, client, prompt_template, total_usage_stats):
    """Generate Javadoc for all items using the quality assessment pipeline.

    Args:
        items_needing_docs: List of items needing documentation
        java_content: Full Java file content
        file_path: Path to the Java source file
        client: Anthropic client
        prompt_template: Prompt template string
        total_usage_stats: Dictionary of total usage stats

    Returns:
        tuple: (items_with_javadoc, alternatives_map)
            - items_with_javadoc: List of items with generated Javadoc
            - alternatives_map: Dict mapping item names to alternative Javadoc versions
    """
    items_with_javadoc = []
    alternatives_map = {}

    for item in items_needing_docs:
        result = process_item_with_pipeline(item, java_content, client, prompt_template, total_usage_stats, file_path)

        if result:
            item['javadoc'] = result['javadoc']
            items_with_javadoc.append(item)

            # Store alternatives if any (now a list of dicts with label and content)
            if result.get('alternatives'):
                alternatives_map[item['name']] = {
                    'item': item,
                    'primary': result['javadoc'],
                    'alternatives': result['alternatives']  # List of {label, content}
                }
        else:
            print(f"❌ Failed to generate Javadoc for {item['name']}")

    return items_with_javadoc, alternatives_map

def process_single_java_file(java_file, client, prompt_template, total_usage_stats):
    """Process a single Java file and return whether it was modified and any alternatives.

    Args:
        java_file: Path to Java file
        client: Anthropic client
        prompt_template: Prompt template string
        total_usage_stats: Dictionary of total usage stats

    Returns:
        tuple: (was_modified, alternatives_map)
            - was_modified: True if file was modified
            - alternatives_map: Dict of alternative Javadoc versions for this file
    """
    print(f"\n{'='*60}")
    print(f"Processing: {java_file}")
    print('='*60)

    try:
        java_content = read_java_file(java_file)
        items_needing_docs = parse_java_file(java_content)

        if not items_needing_docs:
            print(f"No items needing documentation found in {java_file}")
            return False, {}

        print_items_summary(items_needing_docs)
        items_with_javadoc, alternatives_map = generate_all_javadocs(items_needing_docs, java_content, java_file, client, prompt_template, total_usage_stats)

        if items_with_javadoc:
            write_updated_file(java_file, java_content, items_with_javadoc)
            return True, alternatives_map

        return False, {}

    except Exception as e:
        print(f"Error processing {java_file}: {e}\n{traceback.format_exc()}", file=sys.stderr)
        return False, {}

def process_all_files(java_files, client, prompt_template, total_usage_stats):
    """Process all Java files and return list of modified files and alternatives.

    Args:
        java_files: List of Java file paths
        client: Anthropic client
        prompt_template: Prompt template string
        total_usage_stats: Dictionary of total usage stats

    Returns:
        tuple: (files_modified, all_alternatives)
            - files_modified: List of modified file paths
            - all_alternatives: Dict mapping file paths to their alternatives
    """
    files_modified = []
    all_alternatives = {}

    for java_file in java_files:
        was_modified, alternatives_map = process_single_java_file(java_file, client, prompt_template, total_usage_stats)
        if was_modified:
            files_modified.append(java_file)
            if alternatives_map:
                all_alternatives[java_file] = alternatives_map

    return files_modified, all_alternatives

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
    print(f"Items bypassed by heuristics: {total_usage_stats['items_bypassed_by_heuristics']}")
    print(f"Total tokens used: {total_usage_stats['total_tokens']}")
    print(f"Estimated cost: ${total_usage_stats['total_cost']:.4f}")

    if not files_modified:
        print("No files were modified.")
        return

    if commit_after:
        commit_changes(files_modified, total_usage_stats)
    else:
        print(f"\n✅ Successfully modified {len(files_modified)} file(s) in debug mode (no commit)")

def create_alternatives_comment(all_alternatives):
    """Create a markdown comment with alternative Javadoc versions for the PR.

    Args:
        all_alternatives: Dict mapping file paths to their alternatives

    Returns:
        str: Markdown formatted comment with alternatives
    """
    if not all_alternatives:
        return None

    comment_parts = [
        "## Alternative Javadoc Versions Available",
        "",
        "The AI generated multiple Javadoc versions for review. Choose which version to keep:",
        ""
    ]

    for file_path, alternatives_map in all_alternatives.items():
        comment_parts.append(f"### File: `{file_path}`")
        comment_parts.append("")

        for item_name, alternatives_data in alternatives_map.items():
            item = alternatives_data['item']
            comment_parts.append(f"#### {item['type'].capitalize()}: `{item_name}` (line {item['line']})")
            comment_parts.append("")

            # Primary version (currently applied)
            comment_parts.append("**Primary Version (Currently Applied):**")
            comment_parts.append("```java")
            comment_parts.append(alternatives_data['primary'])
            comment_parts.append("```")
            comment_parts.append("")

            # Alternative versions (list of {label, content})
            for alt in alternatives_data['alternatives']:
                label = alt['label']
                content = alt['content']
                comment_parts.append(f"**{label}:**")
                comment_parts.append("```java")
                comment_parts.append(content)
                comment_parts.append("```")
                comment_parts.append("")

    return '\n'.join(comment_parts)

def post_alternatives_to_pr(all_alternatives):
    """Post alternative Javadoc versions as a PR comment using gh CLI.

    Args:
        all_alternatives: Dict mapping file paths to their alternatives
    """
    if not all_alternatives:
        return

    comment = create_alternatives_comment(all_alternatives)
    if not comment:
        return

    try:
        # Write comment to a temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(comment)
            temp_file = f.name

        # Post comment to PR using gh CLI
        result = subprocess.run(
            ['gh', 'pr', 'comment', '--body-file', temp_file],
            capture_output=True,
            text=True,
            check=True
        )

        print(f"\n✅ Posted {len(all_alternatives)} alternative Javadoc version(s) to PR")

        # Clean up temp file
        os.unlink(temp_file)

    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not post alternatives to PR: {e}", file=sys.stderr)
        print(f"  You can manually review the alternatives in the output above", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not post alternatives to PR: {e}", file=sys.stderr)

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

    files_modified, all_alternatives = process_all_files(config['java_files'], client, prompt_template, total_usage_stats)

    print_final_summary(config['java_files'], files_modified, total_usage_stats, config['commit_after'])

    # Post alternatives to PR if in GitHub Action mode and there are alternatives
    if config['commit_after'] and all_alternatives:
        post_alternatives_to_pr(all_alternatives)

if __name__ == "__main__":
    single_file = sys.argv[1] if len(sys.argv) > 1 else None
    main(single_file=single_file)
