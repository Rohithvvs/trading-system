# Prompt 04: Research Synthesis

Use this template to consolidate ideas, address criticisms, and synthesize findings into a coherent proposal.

<input>
- **Target Symbol**: `{{SYMBOL}}`
- **Source Idea ID(s)**: `{{SOURCE_IDEA_IDS}}`
- **Critique Feedback**:
`{{CRITIQUE_FEEDBACK}}`
</input>

<instructions>
Draft the final synthesis of the candidate strategy, resolving or mitigating the issues raised during the adversarial critique.
Structure the output to populate the `research_syntheses` table:
- **Title**: Unified title for the synthesized proposal.
- **Synthesis Text**: Comprehensive description detailing the updated implementation, mitigation measures, and how critiques were addressed.
- **Source Idea IDs**: CSV list of original idea IDs.
- **Confidence Score**: Refined confidence level (0.0 to 100.0) after addressing critiques.
- **Status**: Set to `DRAFT` or `FINAL`.
</instructions>

<expected_output>
Format the proposal using this XML layout:
```xml
<research_synthesis>
  <title>...</title>
  <synthesis_text>...</synthesis_text>
  <source_idea_ids>{{SOURCE_IDEA_IDS}}</source_idea_ids>
  <confidence_score>...</confidence_score>
  <status>FINAL</status>
</research_synthesis>
```
</expected_output>
