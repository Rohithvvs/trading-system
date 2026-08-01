# Prompt 02: Research Idea Generation

Use this template to generate a concrete research candidate idea structured for database persistence.

<input>
- **Target Symbol**: `{{SYMBOL}}`
- **Focus Component**: `{{COMPONENT_TAG}}` (e.g. `COMP-NEWS`, `COMP-REGIME`)
- **Focus Situations**: `{{SITUATION_TAGS}}` (e.g. `SIT-CSE`, `SIT-GN`, `SIT-BN`)
- **Strategy Description**: `{{STRATEGY_DESCRIPTION}}`
</input>

<instructions>
Develop the research strategy candidate based on the focus component and situations.
Structure your proposal to directly populate the `research_ideas` table:
- **Title**: Descriptive title of the strategy enhancement.
- **Description**: Detailed explanation of the signal generation mechanism.
- **Component Tag**: Core component (e.g., `COMP-NEWS`).
- **Situation Tags**: CSV list of applicable situations.
- **Evidence Level**: Initial level (e.g., `LEVEL_0_PROPOSAL`).
- **Lifecycle Stage**: Initial stage (e.g., `PROPOSAL`).
- **Bucket**: Classification bucket (e.g., `ALPHA_DECAY`, `EXECUTION_SLIPPAGE`, `RISK_OVERLAY`).
- **Required Data**: Data feeds and historical features needed.
- **Safe Fallback**: Action to take if required data is missing.
- **Rollback Criteria**: Specific telemetry triggers for automated disabling.
- **Confidence Score**: Initial estimate between 0.0 and 100.0.
</instructions>

<expected_output>
Format your output with explicit XML tags for database insertion:
```xml
<research_idea>
  <title>...</title>
  <description>...</description>
  <component_tag>{{COMPONENT_TAG}}</component_tag>
  <situation_tags>{{SITUATION_TAGS}}</situation_tags>
  <evidence_level>LEVEL_0_PROPOSAL</evidence_level>
  <lifecycle_stage>PROPOSAL</lifecycle_stage>
  <bucket>...</bucket>
  <required_data>...</required_data>
  <safe_fallback>...</safe_fallback>
  <rollback_criteria>...</rollback_criteria>
  <confidence_score>...</confidence_score>
</research_idea>
```
</expected_output>
