from __future__ import annotations

import os
import uuid
import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from ..core.jsonl_store import JsonlStore
from .schema import Alert, AlertCreate, AlertSeverity, AlertCondition


class AlertRule:
    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data["name"]
        self.metric_name: str = data["metric_name"]
        self.condition: AlertCondition = AlertCondition(data["condition"])
        self.threshold: float = float(data["threshold"])
        self.severity: AlertSeverity = AlertSeverity(data["severity"])
        self.message_template: str | None = data.get("message_template")
        self.enabled: bool = data.get("enabled", True)


class AlertEngine:
    def __init__(
        self,
        rules_path: str | Path | None = None,
        base_dir: str | Path | None = None,
    ) -> None:
        if rules_path is None:
            rules_path = os.getenv(
                "ALERT_RULES_PATH",
                str(Path(__file__).parent.parent / "config" / "alerts.yml"),
            )
        if base_dir is None:
            base_dir = os.getenv("ALERT_STORE_DIR", "logs")
        self.rules_path = Path(rules_path)
        self.store = JsonlStore(base_dir, category="alerts")
        self._rules: list[AlertRule] | None = None
        self._last_triggered: dict[str, datetime] = {}
        self._dedup_window_seconds: int = 60

    def load_rules(self) -> list[AlertRule]:
        if self._rules is not None:
            return self._rules
        if not self.rules_path.exists():
            self._rules = []
            return self._rules
        with open(self.rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        self._rules = [AlertRule(item) for item in data]
        return self._rules

    def reload_rules(self) -> list[AlertRule]:
        self._rules = None
        return self.load_rules()

    def evaluate(self, metric_name: str, metric_value: float) -> list[Alert]:
        triggered: list[Alert] = []
        now = datetime.now(timezone.utc)
        for rule in self.load_rules():
            if not rule.enabled:
                continue
            if rule.metric_name != metric_name:
                continue
            if not self._check_condition(metric_value, rule.condition, rule.threshold):
                continue
            if self._is_duplicate(rule.name, now):
                continue
            self._last_triggered[rule.name] = now
            alert = Alert(
                uuid=uuid.uuid4(),
                rule_name=rule.name,
                severity=rule.severity,
                metric_name=metric_name,
                metric_value=metric_value,
                threshold=rule.threshold,
                message=self._format_message(rule, metric_value),
                timestamp=now,
            )
            self.store.append(alert.model_dump(mode="json"))
            triggered.append(alert)
        return triggered

    def evaluate_batch(self, metrics: dict[str, float]) -> list[Alert]:
        all_alerts: list[Alert] = []
        for name, value in metrics.items():
            all_alerts.extend(self.evaluate(name, value))
        return all_alerts

    def query_alerts(
        self,
        severity: AlertSeverity | None = None,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if severity:
            filters["severity"] = severity.value
        return self.store.query(
            start_time=since,
            filters=filters if filters else None,
            limit=limit,
            offset=offset,
        )

    def _check_condition(
        self, value: float, condition: AlertCondition, threshold: float
    ) -> bool:
        if condition == AlertCondition.GT:
            return value > threshold
        elif condition == AlertCondition.LT:
            return value < threshold
        elif condition == AlertCondition.GTE:
            return value >= threshold
        elif condition == AlertCondition.LTE:
            return value <= threshold
        elif condition == AlertCondition.EQ:
            return abs(value - threshold) < 1e-9
        return False

    def _is_duplicate(self, rule_name: str, now: datetime) -> bool:
        if rule_name not in self._last_triggered:
            return False
        elapsed = (now - self._last_triggered[rule_name]).total_seconds()
        return elapsed < self._dedup_window_seconds

    def _format_message(self, rule: AlertRule, metric_value: float) -> str | None:
        if not rule.message_template:
            return None
        return rule.message_template.format(
            metric_value=metric_value,
            threshold=rule.threshold,
            metric_name=rule.metric_name,
        )
