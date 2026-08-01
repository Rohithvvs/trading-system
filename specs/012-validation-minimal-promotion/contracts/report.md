# CLI Interface Contracts: Challenger Validation Report

This contract document specifies the command-line interface schema for generating the Challenger Validation Report.

---

## 1. Validation Report Generation

Generates a validation report for a specific rule based on the last 14 days of shadow mode execution logs.

### Command Syntax
```bash
python -m app.governance.experiment_cli report --rule <rule_id> [--output-dir <directory>]
```

### Arguments
* `--rule` (string, required): The unique ID of the rule to validate (e.g., `news_dedup`).
* `--output-dir` (string, optional): Overrides the default directory (`governance/reports/`) where report JSON and Markdown files are saved.

### Expected Output (Success)
```text
✓ Analysis completed for 'news_dedup' (2026-07-07 to 2026-07-21).
✓ Operational status: PASS
✓ Deduplication Rate: 24.50% (Range: 5% - 40%)
✓ False-Positive Rate: 12.00% (Baseline: 15.00%)
✓ Saved structured report: governance/reports/challenger_report_news_dedup.json
✓ Saved human-readable summary: governance/reports/challenger_report_news_dedup.md
```

### Expected Output (Error - Insufficient Data Warning)
```text
⚠️ WARNING: Under 14 days of shadow data available (found 8 days).
✓ Analysis completed for 'news_dedup' (incomplete window).
✓ Saved structured report: governance/reports/challenger_report_news_dedup.json
```
