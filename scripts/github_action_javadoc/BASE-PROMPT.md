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
Generate documentation for the following Java {item_type}.

ITEM DETAILS:
Name: {item_name}
Signature: {item_signature}
Modifiers: {modifiers}
Parameters: {parameters}
Return Type: {return_type}

ACTUAL CODE TO DOCUMENT:
{implementation_code}

{existing_content}

FULL FILE CONTEXT:
{java_content}

INSTRUCTIONS:
Generate Javadoc documentation ONLY for complex or non-obvious code. Follow best practices:

DOCUMENTATION PHILOSOPHY:
- Document only what needs explanation - simple, self-evident methods should rely on clear naming
- Focus on the contract/API from a user's perspective
- Explain WHY and WHAT, never HOW (no implementation details)
- Be concise - quality over quantity

WHEN TO DOCUMENT:
✓ Complex logic that isn't self-evident
✓ Non-obvious behavior or edge cases
✓ Public APIs with important contracts
✓ Methods with side effects or state changes

WHEN NOT TO DOCUMENT (these are filtered out, but as a guideline):
✗ Simple test methods with obvious assertions
✗ Trivial getters/setters
✗ Methods whose purpose is clear from name and signature
✗ Single-statement methods with obvious behavior

DOCUMENTATION CONTENT:
- Include @param, @return, @throws tags as appropriate (but keep descriptions concise)
- Document *all* invariants, preconditions, postconditions, and side effects
- Explain purpose, behavior, and usage patterns
- Add examples only for complex or ambiguous APIs

OUTPUT FORMAT:
/**
 * [Concise, clear description - typically 1-2 sentences]
 * [Additional context only if needed - edge cases, side effects, usage notes]
 *
 * @param paramName brief description (no redundancy with obvious names)
 * @return brief description of what is returned
 * @throws ExceptionType when this exception occurs
 * @see RelatedClass (only if genuinely relevant)
 */

IMPORTANT RULES:
- Output ONLY the Javadoc comment block, nothing else
- Do NOT include method signatures or implementation code
- Be CONCISE - no redundant information
- Focus on WHAT the code does, not HOW it does it
- Write for API consumers, not maintainers
- Avoid over-explaining obvious parameters or simple behavior
- Class-level documentation: 3-10 lines summarizing purpose and key concepts
- Method-level documentation: 1-5 lines unless truly complex
```
