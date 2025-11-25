# Javadoc Quality Assessment Prompt

You are assessing the quality of a Javadoc comment for a Java {item_type}.

## ITEM DETAILS:
- **Name**: {item_name}
- **Signature**: {item_signature}
- **Modifiers**: {modifiers}

## EXISTING JAVADOC:
```
{existing_javadoc}
```

## IMPLEMENTATION CODE:
```java
{implementation_code}
```

## ASSESSMENT CRITERIA:

Evaluate the Javadoc against these criteria:

### 1. **Accuracy**
- Does the description match what the code actually does?
- Are all behaviors correctly described?
- Are edge cases mentioned if relevant?

### 2. **Completeness**
- Are all parameters documented with @param tags?
- Is the return value documented with @return tag (for non-void methods)?
- Are exceptions documented with @throws tags?
- Are important implementation details explained?

### 3. **Clarity**
- Is the description clear and understandable?
- Does it avoid obvious statements?
- Is it helpful to developers using this code?

### 4. **Format & Style**
- Does it follow proper Javadoc formatting conventions?
- Are line lengths appropriate (check customer requirements)?
- Are tags properly formatted?

### 5. **Parameter Matching**
- For classes: Are there NO @param tags? (Classes should not have @param tags)
- For methods: Does each parameter have exactly one @param tag?
- Do @param tags match actual parameter names?

### 6. **Return Documentation**
- For non-void methods: Is there a meaningful @return tag?
- For void methods: Is there NO @return tag?

## DECISION:

After evaluating all criteria, respond with **ONLY ONE WORD**:

- **"GOOD"** if the Javadoc is adequate and doesn't need improvement
- **"IMPROVE"** if the Javadoc needs to be regenerated

Do not include any explanation, reasoning, or additional text. Just the single word: GOOD or IMPROVE.
