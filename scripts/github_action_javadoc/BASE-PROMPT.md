# Base Javadoc Generation Prompt Template

This file contains the core prompt template used by the Javadoc generation scripts. It includes the fundamental rules and structure that should be consistent across all installations.

## Template Variables
- `{item_type}`: The type of code element (class, method, constructor, etc.)
- `{item_name}`: The name of the code element
- `{item_signature}`: The signature of the code element
- `{implementation_code}`: The actual implementation code of the method/class/constructor
- `{modifiers}`: Access modifiers (public, private, static, etc.)
- `{parameters}`: Parameter information for methods/constructors
- `{return_type}`: Return type for methods
- `{existing_content}`: Any existing Javadoc content that should be preserved/improved
- `{java_content}`: The full content of the Java file for context

## Base Prompt Template

```
You are a Javadoc generator. Generate documentation for this Java {item_type}:

Name: {item_name}
Signature: {item_signature}

IMPLEMENTATION CODE:
{implementation_code}

{existing_content}

REQUIRED OUTPUT:
Generate exactly TWO things:
1. A complete Javadoc comment block (/** ... */)
2. Implementation notes as comments inside the method/class body

OUTPUT FORMAT:
/**
 * [Javadoc describing the contract/behavior]
 * @param [if applicable]
 * @return [if applicable]
 * @throws [if applicable]
 */
public [type] methodName(...) {{
    // Implementation notes: [Explain how the code works internally]
    // [Continue on multiple lines if needed, each starting with //]
}}

[Rest of your rules here...]

EXAMPLE:
/**
 * Merges slots from a partial stack into the final stack with proper offset adjustment.
 * Adds all slots from the new partial stack to the final stack, adjusting their positions
 * to avoid conflicts with existing slots.
 *
 * @param finalStack the target stack to merge into (modified in place)
 * @param newPartialStack the source stack containing slots to add
 * @throws NotImplementedException if any slot in newPartialStack has a negative slot number
 */
public static void merge(Set<Slot> finalStack, Set<Slot> newPartialStack) {{
    // Implementation notes: Calculates offset by finding max slot in finalStack, then adds 1.
    // Iterates through newPartialStack, validates no negative slots (throws if found),
    // then creates new Slot objects with adjusted positions (original + offset) and adds
    // them to finalStack. The FIXME comment suggests offset calculation may be redundant
    // in some cases but is kept for safety.
}}
```
