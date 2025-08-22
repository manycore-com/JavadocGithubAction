# Customer Javadoc Generation Settings

This file contains customer-specific settings that override or extend the base prompt template. Settings here take precedence over BASE-PROMPT.md.

## Customer-Specific Rules

```
CUSTOMER REQUIREMENTS:

*** CRITICAL CLASS DOCUMENTATION RULE ***:
- NEVER EVER use @param tags in class-level JavaDoc comments
- Class JavaDoc should ONLY describe what the class does, not individual fields
- @param is FORBIDDEN for classes - it's only for methods and constructors
- If documenting a class with fields like "radius", describe them in prose, not @param tags

FORMATTING PREFERENCES:
- *** CRITICAL: FORMAT EACH LINE TO BE NO MORE THAN 80 CHARACTERS WIDE ***
- *** MANDATORY: Break long descriptions into multiple lines at word boundaries ***
- Each continuation line must start with " * " (space-asterisk-space)
- COUNT CHARACTERS: Ensure no line exceeds 80 characters including " * " prefix
- WRAP IMMEDIATELY when approaching 80 characters

80-CHARACTER WIDTH EXAMPLES:

METHOD EXAMPLE:
/**
 * Multiplies two 4x4 matrices using standard matrix multiplication.
 * Performs matrix multiplication where the result[i][j] is the dot product
 * of row i from matrix A and column j from matrix B.
 * 
 * @param A the first 4x4 matrix with double elements
 * @param B the second 4x4 matrix with double elements  
 * @return a new 4x4 matrix containing the product of A and B
 * @throws IllegalArgumentException if either matrix is not exactly 4x4
 *                                  dimensions
 * @throws NullPointerException if either A or B is null, or if any row
 *                              is null
 */

CLASS EXAMPLE (NO @throws):
/**
 * Utility class providing mathematical operations for 4x4 matrices.
 * Contains static methods for performing matrix multiplication and other
 * matrix operations using standard algorithms.
 */

DOCUMENTATION STYLE:
- Use specific, implementation-focused descriptions
- Focus on what the code actually does, not generic descriptions
- Include units, constraints, and data type details where relevant
- Document both normal operation and error conditions

GENERATE ONLY THE JAVADOC COMMENT BLOCK NOW:
```

## Customization Options

You can modify the customer requirements above to change:

### Documentation Tags
- Whether to include @param tags (currently: required)
- Whether to include @return tags (currently: required for non-void methods)  
- Whether to include @throws tags (currently: required)
- Additional custom tags like @since, @author, @version

### Formatting Style
- Line width limits (currently: 80 characters)
- Indentation preferences
- Word wrapping behavior

### Content Style
- Writing style (imperative vs. descriptive)
- Level of detail expected
- Whether to document implementation details vs. just interface
- How to handle edge cases and exceptions

### Project-Specific Standards
- Naming conventions for documentation
- Required information for certain types of methods
- Custom validation rules
- Integration with other documentation systems