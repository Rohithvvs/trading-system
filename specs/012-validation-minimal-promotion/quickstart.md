# Quickstart Validation Guide: Validation & Minimal Promotion

This guide contains runnable scenarios to validate that the Validation Report, Rule Manager, and Controlled Promotion Path behave correctly end-to-end.

---

## 1. Prerequisites
* Virtual environment active and python dependencies installed.
* Database running and initialized with seed data (e.g., at least some historical recommendation and shadow execution logs).
* Audit log directory `logs/` exists.

---

## 2. Validation Scenario 1: Generate Validation Report

Verify that the operator can query and generate validation metrics based on shadow execution telemetry.

### Execution Command
```bash
python -m app.governance.experiment_cli report --rule news_dedup
```

### Verification Steps
1. Verify `governance/reports/challenger_report_news_dedup.json` is created and contains valid JSON matching the [Validation Report Schema](file:///D:/Work_Space/trading-system/specs/012-validation-minimal-promotion/data-model.md#2-challenger-validation-report-schema-challenger_report_news_dedupjson).
2. Verify `governance/reports/challenger_report_news_dedup.md` is created and displays the summary details.
3. Check the command output for the status (e.g., `PASS` or `FAIL`).

---

## 3. Validation Scenario 2: Promote a Rule

Verify that an authorized human can promote the `news_dedup` rule with the checklist assertion flag.

### Execution Command
```bash
python -m app.governance.experiment_cli promote --rule news_dedup --checklist-approved --reason "14-day shadow window is complete and checklist is verified"
```

### Verification Steps
1. Verify that `backend/app/config/rule_states.json` has updated `"news_dedup"` to `"production"`.
2. Inspect the tail of `logs/audit.jsonl` to ensure a `"rule.promote"` action was logged under the actor `"admin"`.
3. Run a recommendation check or scan, and verify in `logs/app.log` that `deduplicate_articles` is running *in-line* for the production sentiment pipeline rather than in the shadow thread pool.

---

## 4. Validation Scenario 3: Emergency Kill Switch

Verify that the operator can instantly disable a rule in production.

### Execution Command
```bash
python -m app.governance.experiment_cli kill --rule news_dedup --reason "Emergency rollback: sentiment anomalies detected"
```

### Verification Steps
1. Verify that `backend/app/config/rule_states.json` has updated `"news_dedup"` to `"disabled"`.
2. Inspect the tail of `logs/audit.jsonl` to ensure a `"rule.kill"` action was logged.
3. Run a recommendation check, and verify in the logs that deduplication is bypassed entirely and the original, undeduplicated articles list is passed to production sentiment scoring.
