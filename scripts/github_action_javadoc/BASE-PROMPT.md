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
Generate comprehensive Javadoc documentation that describes WHAT the code does:

- Focus on the contract/API from a user's perspective
- Include @param, @return, @throws tags as appropriate
- NO implementation details - just the public contract
- Explain the purpose, behavior, and usage
- Document *all* invariant, preconditions, postconditions, and side effects

OUTPUT FORMAT:
/**
 * [Clear description of what this class/method/constructor does]
 * [Additional details about behavior, usage patterns, or important notes]
 * [Include examples if helpful for complex APIs]
 *
 * @param paramName parameter description for users
 * @return what is returned to the caller
 * @throws ExceptionType when this exception is thrown
 * @see RelatedClass or method for cross-references
 * @since version when this was added
 */

IMPORTANT:
- Output ONLY the Javadoc comment block, nothing else
- Do NOT include method signatures or implementation code
- Focus on WHAT the code does, not HOW it does it
- Write for API consumers, not maintainers
- Use clear, concise language
- Include examples for complex or non-obvious APIs
```
