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
Generate TWO separate documentation blocks:

1. A Javadoc comment (/** ... */) that describes WHAT the code does
   - Focus on the contract/API from a user's perspective
   - Include @param, @return, @throws tags as appropriate
   - NO implementation details - just the public contract

2. An implementation notes comment (/* AI Implementation Notes: ... */) for methods/constructors
   - Explain HOW the code works internally
   - Include algorithm details, data structures, complexity analysis
   - Describe state changes, edge cases, important logic flow
   - This serves as a "state dump" for AI systems

OUTPUT FORMAT:
For classes, generate ONLY the Javadoc:
/**
 * [Description of what this class represents]
 * [Additional details about the class purpose and usage]
 */

For methods and constructors, generate BOTH blocks:
/**
 * [Description of what this method/constructor does]
 * [Additional details about behavior/contract]
 * 
 * @param paramName parameter description for users
 * @return what is returned to the caller
 * @throws ExceptionType when this exception is thrown
 */
/* AI Implementation Notes:
 * [Detailed explanation of HOW it works internally]
 * [Algorithm steps, data structures used, complexity analysis]
 * [State changes, edge cases handled, important logic flow]
 */

IMPORTANT:
- Output ONLY these documentation blocks, nothing else
- Do NOT include method signatures or code
- Keep Javadoc focused on WHAT (the contract)
- Keep implementation notes focused on HOW (the internals)
- For classes, only generate Javadoc (no implementation notes)
- For methods/constructors, generate both blocks as shown above
```
