# Prompt 03: Adversarial Critique

Use this template to subject a candidate research idea to strict risk, execution, and data sanity checks.

<input>
- **Target Symbol**: `{{SYMBOL}}`
- **Proposed Research Idea**:
`{{RESEARCH_IDEA_XML}}`
</input>

<instructions>
Perform an adversarial critique of the proposed trading strategy candidate.
Identify structural vulnerabilities, implementation bottlenecks, and data leakage risks.
Directly populate the fields of the `research_critiques` table:
- **Critique Type**: Category of critique (e.g. `DATA_BIAS`, `LATENCY_SLIPPAGE`, `CAPACITY_LIMITS`).
- **Content**: Detailed explanation of the critique.
- **Severity**: Risk severity level (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **Resolved**: Initial status (MUST be `false`).
</instructions>

<expected_output>
Format your critiques as a sequence of XML blocks:
```xml
<research_critiques>
  <critique>
    <critique_type>...</critique_type>
    <content>...</content>
    <severity>...</severity>
    <resolved>false</resolved>
  </critique>
</research_critiques>
```
</expected_output>
