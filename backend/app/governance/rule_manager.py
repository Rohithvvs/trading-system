from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Literal

from ..config import settings
from .audit import AuditTrailManager

logger = logging.getLogger("app.governance")

RuleState = Literal["shadow", "production", "disabled"]

# Fail-safe lifecycle state when the state store cannot be read reliably.
# Spec edge case: pipeline must default to baseline (undeduplicated) behavior.
FAIL_SAFE_STATE: RuleState = "disabled"


class RuleManager:
    """Manages the lifecycle state of experimental rules (shadow, production, disabled).

    Reads/writes states from rule_states.json and caches them in memory.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (primarily for testing)."""
        with cls._lock:
            cls._instance = None

    def __init__(self, states_file: str | Path | None = None) -> None:
        # If we explicitly pass a new states_file, re-initialize
        if self._initialized and states_file is None:
            return

        # Resolve rule states file path
        if states_file is not None:
            self.states_file = Path(states_file)
            self._states: dict[str, RuleState] = {}
            self._store_unavailable = False
            self._cache_lock = threading.RLock()
            # Serializes promote/kill so concurrent admin actions run in order.
            # Kill issued while promote is in-flight waits, then applies disabled last.
            self._transition_lock = threading.RLock()
            self.audit_mgr = AuditTrailManager()
            self._load_states()
            self._initialized = True
            return

        if not hasattr(self, "states_file"):
            raw_path = settings.rule_states_file
            # If path is relative, resolve it from repository root
            from ..config.settings import ROOT_DIR
            path_obj = Path(raw_path)
            if not path_obj.is_absolute():
                self.states_file = ROOT_DIR / path_obj
            else:
                self.states_file = path_obj

        self._states = {}
        self._store_unavailable = False
        self._cache_lock = threading.RLock()
        self._transition_lock = threading.RLock()
        self.audit_mgr = AuditTrailManager()
        self._load_states()
        self._initialized = True

    def _mark_store_unavailable(self, reason: str) -> None:
        """Mark the state store unusable and emit a high-priority alert."""
        self._store_unavailable = True
        self._states = {}
        logger.error(
            "CRITICAL: Rule state store unavailable (%s). "
            "Fail-safe active: all rule lookups default to '%s' (baseline pipeline).",
            reason,
            FAIL_SAFE_STATE,
        )

    def _load_states(self) -> None:
        """Synchronously load rule states from file into cache."""
        with self._cache_lock:
            self._store_unavailable = False
            if not self.states_file.exists():
                # Fresh install / empty store is available but has no entries.
                # Unknown rules still default to shadow until explicitly configured.
                logger.info(
                    "Rule states file %s does not exist; using empty mapping (default shadow)",
                    self.states_file,
                )
                self._states = {}
                return

            try:
                with open(self.states_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._states = {
                            k: v
                            for k, v in data.items()
                            if v in ("shadow", "production", "disabled")
                        }
                    else:
                        self._mark_store_unavailable(
                            f"invalid schema in {self.states_file} (expected JSON object)"
                        )
            except Exception as e:
                self._mark_store_unavailable(f"failed to load {self.states_file}: {e}")

    def _save_states(self) -> None:
        """Atomically persist cached states to disk.

        Writes to a temporary file then replaces the target to avoid partial JSON
        on crash. Raises RuntimeError on failure so callers do not claim success.
        """
        with self._cache_lock:
            snapshot = dict(self._states)
            target = self.states_file

        tmp_path = target.with_suffix(target.suffix + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    # fsync not supported on some filesystems; replace still helps.
                    pass
            os.replace(tmp_path, target)
            with self._cache_lock:
                self._store_unavailable = False
        except Exception as e:
            # Best-effort cleanup of temp file
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            logger.error(
                "CRITICAL: Failed to persist rule states to %s: %s. "
                "In-memory state may diverge from disk until the next successful write.",
                target,
                e,
            )
            raise RuntimeError(
                f"Failed to persist rule states to {target}: {e}"
            ) from e

    def get_rule_state(self, rule_id: str) -> RuleState:
        """Get the current lifecycle state of a rule.

        - Known rules: return cached lifecycle state.
        - Unknown rules when store is healthy: default to ``shadow``.
        - Store unavailable / unreadable: fail-safe ``disabled`` (baseline path).
        """
        try:
            with self._cache_lock:
                if self._store_unavailable:
                    return FAIL_SAFE_STATE
                # news_dedup default after healthy deploy remains shadow until promoted.
                return self._states.get(rule_id, "shadow")
        except Exception as e:
            logger.error(
                "CRITICAL: Rule state lookup failed for '%s': %s. Fail-safe '%s'.",
                rule_id,
                e,
                FAIL_SAFE_STATE,
            )
            return FAIL_SAFE_STATE

    def is_active_in_production(self, rule_id: str) -> bool:
        """Check if a rule is active in production. Resolves under 1ms via local cache."""
        return self.get_rule_state(rule_id) == "production"

    def is_store_unavailable(self) -> bool:
        """Return True when the state store failed to load and fail-safe is active."""
        with self._cache_lock:
            return self._store_unavailable

    async def _record_transition_audit(
        self,
        *,
        actor: str,
        action: str,
        rule_id: str,
        previous_state: str,
        new_state: str,
        reason: str,
        checklist_approved: bool | None = None,
        attribution_report_approved: bool | None = None,
    ) -> None:
        """Best-effort audit write; state transition must not roll back on audit failure."""
        details: dict[str, object] = {
            "previous_state": previous_state,
            "new_state": new_state,
            "reason": reason,
        }
        if checklist_approved is not None:
            details["checklist_approved"] = checklist_approved
        if attribution_report_approved is not None:
            details["attribution_report_approved"] = attribution_report_approved
        try:
            await self.audit_mgr.record(
                actor=actor,
                action=action,
                target_type="rule",
                target_id=rule_id,
                outcome="success",
                details=details,
            )
        except Exception as e:
            logger.error(
                "CRITICAL: Failed to append audit event for %s on rule %s "
                "(state already %s): %s",
                action,
                rule_id,
                new_state,
                e,
            )

    async def promote_rule(
        self,
        rule_id: str,
        checklist_approved: bool,
        reason: str = "",
        actor: str = "admin",
        attribution_report_approved: bool | None = None,
    ) -> None:
        """Promote a rule from 'shadow' to 'production'.

        Enforces checklist verification before state modification.
        Serialized with kill via ``_transition_lock`` (sequential admin actions).

        Sprint 8 gates (centralized here so REST and CLI cannot diverge):
        - SC-001: sentiment_decay / market_breadth require attribution_report_approved
        - FR-008: market_breadth (Stage 2) requires sentiment_decay already in production
        """
        if not checklist_approved:
            raise ValueError(
                "Rule promotion rejected. Must verify review checklist completion using the --checklist-approved flag."
            )

        # SC-001: candidate Sprint-8 features require completed attribution report approval
        if rule_id in ("sentiment_decay", "market_breadth"):
            if attribution_report_approved is not True:
                raise ValueError(
                    f"Rule promotion rejected for '{rule_id}'. "
                    "SC-001 requires attribution_report_approved=True "
                    "(complete A/B attribution report and interaction check)."
                )

        # FR-008: Stage 2 blocked until Stage 1 is live
        if rule_id == "market_breadth":
            if not self.is_active_in_production("sentiment_decay"):
                raise ValueError(
                    "Stage 2 promotion ('market_breadth') blocked: "
                    "Stage 1 ('sentiment_decay') must be promoted to production first."
                )

        with self._transition_lock:
            current_state = self.get_rule_state(rule_id)
            if current_state == "production" and not self.is_store_unavailable():
                logger.info("Rule %s is already in production", rule_id)
                return

            # Safety: do not silently promote over a fail-safe/disabled store without
            # first writing a healthy production entry (operator explicit promote).
            with self._cache_lock:
                self._states[rule_id] = "production"
                self._store_unavailable = False

            self._save_states()
            logger.info(
                "Rule %s promoted to production by %s (previous_state=%s)",
                rule_id,
                actor,
                current_state,
            )

        await self._record_transition_audit(
            actor=actor,
            action="rule.promote",
            rule_id=rule_id,
            previous_state=current_state,
            new_state="production",
            reason=reason,
            checklist_approved=True,
            attribution_report_approved=(
                True if attribution_report_approved is True else attribution_report_approved
            ),
        )

    async def kill_rule(self, rule_id: str, reason: str, actor: str = "admin") -> None:
        """Emergency rollback/kill-switch to transition rule state to 'disabled'.

        Serialized with promote via ``_transition_lock``. When promote and kill
        race, the later lock holder wins; a kill issued during promote waits and
        then forces ``disabled`` (kill takes final effect for in-flight pairs).
        """
        if not reason:
            raise ValueError("A reason must be provided to disable/kill a rule.")

        with self._transition_lock:
            current_state = self.get_rule_state(rule_id)
            with self._cache_lock:
                self._states[rule_id] = "disabled"
                self._store_unavailable = False

            self._save_states()
            logger.info(
                "Rule %s DISABLED by %s (previous_state=%s). Reason: %s",
                rule_id,
                actor,
                current_state,
                reason,
            )

        await self._record_transition_audit(
            actor=actor,
            action="rule.kill",
            rule_id=rule_id,
            previous_state=current_state,
            new_state="disabled",
            reason=reason,
        )
