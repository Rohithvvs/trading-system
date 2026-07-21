# Prompt 01: Research Context Injection

Use this template to initialize a new research session for a strategy idea.

<input>
- **Target Symbol**: `{{SYMBOL}}`
- **Session Label**: `{{SESSION_LABEL}}`
- **Idea Summary**: `{{IDEA_SUMMARY}}`
</input>

<instructions>
We are initiating a research session inside our algorithmic trading system.
Configure a new research session matching the `research_sessions` database entity:
- Session Label: "{{SESSION_LABEL}}"
- Target Symbol: "{{SYMBOL}}"
- Status: "ACTIVE"
- Metadata: JSON dictionary storing current market environment variables (e.g., date, base regime).

Verify that all baseline conditions are met and output the current context state within the `<context_state>` tag.
</instructions>

<expected_output>
Format your output in Markdown with the following XML section block:
```xml
<context_state>
  <session_label>{{SESSION_LABEL}}</session_label>
  <symbol>{{SYMBOL}}</symbol>
  <status>ACTIVE</status>
  <initial_hypothesis>{{IDEA_SUMMARY}}</initial_hypothesis>
</context_state>
```
</expected_output>
