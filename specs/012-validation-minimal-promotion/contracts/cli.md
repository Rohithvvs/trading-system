# CLI Interface Contracts: Rule Promotion & Rollback

This contract document specifies the command-line interface schemas for promoting and disabling rules via the governance CLI.

---

## 1. Rule Promotion

Promotes an experimental rule from `shadow` state into `production` execution.

### Command Syntax
```bash
python -m app.governance.experiment_cli promote --rule <rule_id> --checklist-approved [--reason "<reason>"]
```

### Arguments
* `--rule` (string, required): The unique ID of the rule to promote (e.g., `news_dedup`).
* `--checklist-approved` (flag, required): Confirms completion of `docs/FEAT_010_REVIEW_CHECKLIST.md`.
* `--reason` (string, optional): Contextual notes or review justification for the audit trail.

### Expected Output (Success)
```text
✓ Rule 'news_dedup' successfully promoted to PRODUCTION.
✓ State transition logged to audit log.
```

### Expected Output (Error - Missing Checklist Approval)
```text
ERROR: Rule promotion rejected. 
Must verify review checklist completion using the --checklist-approved flag.
Please review: docs/FEAT_010_REVIEW_CHECKLIST.md
```

---

## 2. Rule Rollback (Kill Switch)

Immediately disables a promoted rule, transitioning its state to `disabled` to revert to baseline behavior.

### Command Syntax
```bash
python -m app.governance.experiment_cli kill --rule <rule_id> --reason "<reason>"
```

### Arguments
* `--rule` (string, required): The unique ID of the rule to disable (e.g., `news_dedup`).
* `--reason` (string, required): Reason for triggering the emergency rollback (written to audit trail).

### Expected Output (Success)
```text
✓ Rule 'news_dedup' successfully DISABLED.
✓ Emergency rollback logged to audit trail.
```
