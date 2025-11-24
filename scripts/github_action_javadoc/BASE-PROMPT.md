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
Generate a Javadoc comment (/** ... */) that describes the code:
- Focus on the contract/API from a user's perspective
- Include @param, @return, @throws tags as appropriate
- Describe what the code does and its behavior
- Base your description on what the code ACTUALLY does

OUTPUT FORMAT:
/**
 * [Description of what this class/method/constructor does]
 * [Additional details about behavior and usage]
 *
 * @param paramName parameter description (for methods/constructors)
 * @return what is returned (for non-void methods)
 * @throws ExceptionType when this exception is thrown
 */

IMPORTANT:
- Output ONLY the Javadoc comment block, nothing else
- Do NOT include method signatures or code
- No explanatory text before or after the Javadoc
```
