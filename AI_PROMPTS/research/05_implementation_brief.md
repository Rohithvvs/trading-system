# Prompt 05: Implementation Brief

Use this template to transition a synthesized strategy proposal into a structured decision and define its shadow rollout phases.

<input>
- **Target Symbol**: `{{SYMBOL}}`
- **Synthesized Proposal XML**:
`{{SYNTHESIS_XML}}`
</input>

<instructions>
Formulate the execution decision and rollout checklist for the proposed strategy.
Directly map the details to the `research_decisions` and `research_rollout_states` schemas:
- **Decision Type**: E.g., `DEPLOY_SHADOW`, `REJECT_IDEA`, `REQUEST_BACKTEST`.
- **Rationale**: Core reasoning backing this decision.
- **Rollout Phase**: E.g., `PHASE_A_SHADOW`, `PHASE_B_PAPER`, `PHASE_C_LIVE`.
- **Gating Checks**: Essential performance or metric gates that must be satisfied before progressing to subsequent phases.
</instructions>

<expected_output>
Format the implementation plan using these nested XML tags:
```xml
<implementation_brief>
  <decision>
    <decision_type>DEPLOY_SHADOW</decision_type>
    <rationale>...</rationale>
    <status>PENDING</status>
  </decision>
  <rollout_state>
    <rollout_phase>PHASE_A_SHADOW</rollout_phase>
    <status>PENDING</status>
    <observations>Initial deployment under shadow execution to track divergence and verify performance.</observations>
    <gating_checks_passed>false</gating_checks_passed>
  </rollout_state>
</implementation_brief>
```
</expected_output>
