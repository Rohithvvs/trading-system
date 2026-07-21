"""CLI command handlers for experiment governance.

Usage:
    python -m app.governance.experiment_cli start --name "<name>"
    python -m app.governance.experiment_cli pause
    python -m app.governance.experiment_cli resume
    python -m app.governance.experiment_cli complete
    python -m app.governance.experiment_cli list [--status active]
    python -m app.governance.experiment_cli show <uuid>
    python -m app.governance.experiment_cli metric --name <name> --value <val>
    python -m app.governance.experiment_cli audit export --format json|csv
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone

from ..db.session import AsyncSessionLocal
from .experiment import (
    ExperimentService,
    ExperimentError,
    SingleActiveConstraintError,
    TerminalStateError,
    ExperimentNotFoundError,
)
from .experiment_log import ExperimentLog
from .audit import AuditTrailManager
from ..observability.schema import ExperimentStatus, ExperimentFilterParams

# Privileged taxonomy/backfill commands require Administrator credentials (FR-004 / M7)
_TAXONOMY_ADMIN_COMMANDS = frozenset(
    {
        "backfill",
        "backfill-pause",
        "taxonomy-report",
        "taxonomy-query",
    }
)


def _require_taxonomy_admin(args: argparse.Namespace) -> None:
    """M7: Gate taxonomy admin commands when API_KEY / GOVERNANCE_ADMIN_TOKEN is set.

    Phase 0: if no server-side admin secret is configured, allow with a stderr notice
    (host-trusted ops). When configured, require matching --admin-token or
    GOVERNANCE_CLI_TOKEN environment variable.
    """
    if getattr(args, "command", None) not in _TAXONOMY_ADMIN_COMMANDS:
        return

    expected = (
        os.getenv("GOVERNANCE_ADMIN_TOKEN", "").strip()
        or os.getenv("API_KEY", "").strip()
    )
    if not expected:
        print(
            "[WARN] Taxonomy admin command running without API_KEY/GOVERNANCE_ADMIN_TOKEN "
            "(Phase 0 open host access).",
            file=sys.stderr,
        )
        return

    provided = (
        getattr(args, "admin_token", None)
        or os.getenv("GOVERNANCE_CLI_TOKEN", "")
        or ""
    ).strip()
    if provided != expected:
        print(
            "ERROR: Administrator credentials required for this command. "
            "Pass --admin-token <token> or set GOVERNANCE_CLI_TOKEN to match "
            "API_KEY / GOVERNANCE_ADMIN_TOKEN.",
            file=sys.stderr,
        )
        sys.exit(1)


def _parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Experiment governance CLI",
        prog="experiment",
    )
    sub = parser.add_subparsers(dest="command")

    # start
    start_p = sub.add_parser("start", help="Start a new experiment")
    start_p.add_argument("--name", required=True, help="Experiment name")
    start_p.add_argument("--metadata", help="JSON metadata string")

    # pause
    pause_p = sub.add_parser("pause", help="Pause an active experiment")
    pause_p.add_argument("--id", dest="experiment_id", help="Experiment UUID")

    # resume
    resume_p = sub.add_parser("resume", help="Resume a paused experiment")
    resume_p.add_argument("--id", dest="experiment_id", help="Experiment UUID")

    # complete
    complete_p = sub.add_parser("complete", help="Complete an experiment")
    complete_p.add_argument("--id", dest="experiment_id", help="Experiment UUID")

    # fail
    fail_p = sub.add_parser("fail", help="Mark an experiment as failed")
    fail_p.add_argument("--id", dest="experiment_id", help="Experiment UUID")
    fail_p.add_argument("--reason", help="Failure reason")

    # list
    list_p = sub.add_parser("list", help="List experiments")
    list_p.add_argument("--status", choices=[s.value for s in ExperimentStatus])
    list_p.add_argument("--since", help="ISO date filter")
    list_p.add_argument("--name", help="Name filter")
    list_p.add_argument("--limit", type=int, default=20)
    list_p.add_argument("--offset", type=int, default=0)

    # show
    show_p = sub.add_parser("show", help="Show experiment details")
    show_p.add_argument("experiment_id", help="Experiment UUID")

    # metric
    metric_p = sub.add_parser("metric", help="Add a metric observation")
    metric_p.add_argument("--name", required=True, help="Metric name")
    metric_p.add_argument("--value", type=float, required=True, help="Metric value")
    metric_p.add_argument("--unit", help="Unit of measurement")
    metric_p.add_argument("--tags", help="JSON tags")

    # audit
    audit_p = sub.add_parser("audit", help="Audit trail commands")
    audit_sub = audit_p.add_subparsers(dest="audit_command")
    export_p = audit_sub.add_parser("export", help="Export audit trail")
    export_p.add_argument(
        "--format", choices=["json", "csv"], default="json"
    )
    export_p.add_argument("--since", help="ISO start date")
    export_p.add_argument("--until", help="ISO end date")
    export_p.add_argument("--output", help="Output file path")

    # report
    report_p = sub.add_parser("report", help="Generate validation report")
    report_p.add_argument("--rule", required=True, help="Rule ID (e.g. news_dedup)")
    report_p.add_argument("--output-dir", help="Override output directory")

    # promote
    promote_p = sub.add_parser("promote", help="Promote a rule to production")
    promote_p.add_argument("--rule", required=True, help="Rule ID (e.g. news_dedup)")
    promote_p.add_argument("--checklist-approved", action="store_true", help="Confirm completion of FEAT-010 review checklist")
    promote_p.add_argument("--reason", default="", help="Justification/notes")

    # kill
    kill_p = sub.add_parser("kill", help="Disable a rule")
    kill_p.add_argument("--rule", required=True, help="Rule ID (e.g. news_dedup)")
    kill_p.add_argument("--reason", required=True, help="Reason for emergency rollback")

    # backfill
    backfill_p = sub.add_parser("backfill", help="Run historical situation taxonomy backfill")
    backfill_p.add_argument("--job-id", required=True, help="Unique identifier for the backfill job")
    backfill_p.add_argument("--batch-size", type=int, default=100, help="Number of records to process per batch")
    backfill_p.add_argument("--delay", type=float, default=0.5, help="Throttle delay in seconds between batches")
    backfill_p.add_argument("--resume", action="store_true", help="Resume a previously paused backfill job")
    backfill_p.add_argument(
        "--admin-token",
        default=None,
        help="Administrator token (or set GOVERNANCE_CLI_TOKEN); required when API_KEY is set",
    )

    # backfill-pause (M3)
    pause_bf_p = sub.add_parser(
        "backfill-pause",
        help="Pause a running historical situation taxonomy backfill job",
    )
    pause_bf_p.add_argument("--job-id", required=True, help="Backfill job id to pause")
    pause_bf_p.add_argument("--admin-token", default=None, help="Administrator token")

    # taxonomy-report
    report_tax_p = sub.add_parser("taxonomy-report", help="Generate situation tag distribution report")
    report_tax_p.add_argument("--output-dir", help="Override output directory for the report markdown")
    report_tax_p.add_argument("--admin-token", default=None, help="Administrator token")

    # taxonomy-query (M6 / FR-007)
    query_p = sub.add_parser(
        "taxonomy-query",
        help="Query recommendations by situation tags, action, and date range",
    )
    query_p.add_argument(
        "--tags",
        required=True,
        help="Comma-separated situation tags (all must match)",
    )
    query_p.add_argument(
        "--recommendation",
        default=None,
        help="Filter by action (BUY, SELL, WATCH, ...)",
    )
    query_p.add_argument(
        "--start",
        default=None,
        help="Inclusive start datetime ISO-8601 (created_at)",
    )
    query_p.add_argument(
        "--end",
        default=None,
        help="Inclusive end datetime ISO-8601 (created_at)",
    )
    query_p.add_argument("--limit", type=int, default=50, help="Max rows to return")
    query_p.add_argument("--admin-token", default=None, help="Administrator token")

    return parser.parse_args(args)


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "N/A"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _print_table(rows: list[dict]) -> None:
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        if not rows:
            console.print("[yellow]No experiments found[/yellow]")
            return
        table = Table(show_header=True, header_style="bold cyan")
        for key in rows[0]:
            table.add_column(key.replace("_", " ").title())
        for row in rows:
            table.add_row(*[str(v) for v in row.values()])
        console.print(table)
    except ImportError:
        if not rows:
            print("No experiments found")
            return
        headers = list(rows[0].keys())
        header_str = "  ".join(h.ljust(36) if i == 0 else h.ljust(20) for i, h in enumerate(headers))
        print(header_str)
        print("  " + "  ".join("─" * (36 if i == 0 else 20) for i in range(len(headers))))
        for row in rows:
            print("  ".join(str(v).ljust(36) if i == 0 else str(v).ljust(20) for i, v in enumerate(row.values())))


async def _run_command(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        log = ExperimentLog()
        audit = AuditTrailManager()
        svc = ExperimentService(db, experiment_log=log, audit_mgr=audit)

        try:
            if args.command == "start":
                metadata = None
                if args.metadata:
                    try:
                        metadata = json.loads(args.metadata)
                    except json.JSONDecodeError as e:
                        print(f"Error: Invalid metadata JSON — {e}", file=sys.stderr)
                        sys.exit(1)
                experiment = await svc.create(
                    name=args.name, metadata=metadata
                )
                print(
                    f"Experiment '{experiment.name}' started (ID: {experiment.id})"
                )

            elif args.command == "pause":
                eid = uuid.UUID(args.experiment_id) if args.experiment_id else None
                experiment = await svc.pause(experiment_id=eid)
                print(f"Experiment '{experiment.name}' paused")

            elif args.command == "resume":
                eid = uuid.UUID(args.experiment_id) if args.experiment_id else None
                experiment = await svc.resume(experiment_id=eid)
                print(f"Experiment '{experiment.name}' resumed")

            elif args.command == "complete":
                eid = uuid.UUID(args.experiment_id) if args.experiment_id else None
                experiment = await svc.complete(experiment_id=eid)
                duration_str = _format_duration(experiment.duration_seconds)
                print(
                    f"Experiment '{experiment.name}' completed. Duration: {duration_str}."
                )

            elif args.command == "fail":
                eid = uuid.UUID(args.experiment_id) if args.experiment_id else None
                experiment = await svc.fail(
                    experiment_id=eid, reason=args.reason
                )
                print(f"Experiment '{experiment.name}' marked as failed")

            elif args.command == "list":
                since = None
                if args.since:
                    since = datetime.fromisoformat(args.since)
                fparams = ExperimentFilterParams(
                    status=args.status,
                    since=since,
                    name=args.name,
                    limit=args.limit,
                    offset=args.offset,
                )
                experiments = await svc.list_experiments(
                    status=fparams.status.value if fparams.status else None,
                    since=fparams.since,
                    name=fparams.name,
                    limit=fparams.limit,
                    offset=fparams.offset,
                )
                rows = []
                for exp in experiments:
                    dur = _format_duration(exp.duration_seconds)
                    rows.append({
                        "ID": str(exp.id),
                        "Name": exp.name,
                        "Status": exp.status,
                        "Started": (
                            exp.started_at.strftime("%Y-%m-%d %H:%M:%S")
                            if exp.started_at else ""
                        ),
                        "Duration": dur,
                    })
                _print_table(rows)

            elif args.command == "show":
                eid = uuid.UUID(args.experiment_id)
                experiment = await svc.get(eid)
                if not experiment:
                    print(f"Error: Experiment not found: {eid}", file=sys.stderr)
                    sys.exit(1)
                dur = _format_duration(experiment.duration_seconds)
                print(f"Experiment: {experiment.name} ({experiment.id})")
                print(
                    f"Status: {experiment.status}  |  "
                    f"Started: {experiment.started_at.strftime('%Y-%m-%d %H:%M:%S') if experiment.started_at else 'N/A'}  |  "
                    f"Duration: {dur}"
                )
                metrics = log.get_metrics_for_experiment(str(experiment.id))
                if metrics:
                    print("Metrics:")
                    for m in metrics:
                        print(f"  {m.get('name')}: {m.get('value')}{m.get('unit', '')}")

            elif args.command == "metric":
                tags = None
                if args.tags:
                    try:
                        tags = json.loads(args.tags)
                    except json.JSONDecodeError as e:
                        print(f"Error: Invalid tags JSON — {e}", file=sys.stderr)
                        sys.exit(1)
                metric = await svc.add_metric(
                    name=args.name,
                    value=args.value,
                    unit=args.unit,
                    tags=tags,
                )
                print(
                    f"Metric '{metric['name']}' = {metric['value']} recorded "
                    f"(UUID: {metric['uuid']})"
                )

            elif args.command == "audit":
                if args.audit_command == "export":
                    since = None
                    if args.since:
                        since = datetime.fromisoformat(args.since)
                    until = None
                    if args.until:
                        until = datetime.fromisoformat(args.until)
                    if args.output:
                        # Stream to file (avoids buffering entire export in memory)
                        if args.format == "json":
                            if since or until:
                                events = audit.query(
                                    start_time=since,
                                    end_time=until,
                                    limit=10**9,
                                )
                                with open(args.output, "w", encoding="utf-8") as f:
                                    json.dump(
                                        events,
                                        f,
                                        default=str,
                                        ensure_ascii=False,
                                        indent=2,
                                    )
                            else:
                                audit.store.export_json_to_file(args.output)
                        else:
                            if since or until:
                                events = audit.query(
                                    start_time=since,
                                    end_time=until,
                                    limit=10**9,
                                )
                                if not events:
                                    with open(args.output, "w", encoding="utf-8") as f:
                                        f.write("")
                                else:
                                    headers = list(events[0].keys())
                                    with open(args.output, "w", encoding="utf-8") as f:
                                        f.write(",".join(headers) + "\n")
                                        for event in events:
                                            row = [
                                                audit.store._csv_escape(event.get(h, ""))
                                                for h in headers
                                            ]
                                            f.write(",".join(row) + "\n")
                            else:
                                audit.store.export_csv_to_file(args.output)
                        print(f"Audit trail exported to {args.output}")
                    else:
                        events = audit.query(
                            start_time=since,
                            end_time=until,
                            limit=10000,
                        )
                        if args.format == "json":
                            print(
                                json.dumps(
                                    events, default=str, ensure_ascii=False, indent=2
                                )
                            )
                        else:
                            if not events:
                                print("")
                            else:
                                headers = list(events[0].keys())
                                print(",".join(headers))
                                for event in events:
                                    row = [
                                        audit.store._csv_escape(event.get(h, ""))
                                        for h in headers
                                    ]
                                    print(",".join(row))

            elif args.command == "report":
                from ..services.validation_report import ValidationReportGenerator
                from ..config import settings
                from pathlib import Path
                generator = ValidationReportGenerator(db)
                print(f"Generating Challenger Validation Report for '{args.rule}'...")
                report = await generator.generate_report(args.rule)
                print(f"[OK] Analysis completed for '{args.rule}' ({report['window_start'][:10]} to {report['window_end'][:10]}).")
                print(f"[OK] Operational status: {report['status']}")
                print(f"[OK] Deduplication Rate: {float(report['deduplication_rate'])*100:.2f}% (Range: 5% - 40%)")
                print(f"[OK] False-Positive Rate: {float(report['false_positive_rate'])*100:.2f}% (Baseline: {float(report['baseline_false_positive_rate'])*100:.2f}%)")
                if report.get("data_incomplete") and report.get("incomplete_data_warning"):
                    print(f"[WARN] {report['incomplete_data_warning']}")
                    if report.get("available_data_span_days") is not None:
                        print(
                            f"[WARN] Available shadow data span: "
                            f"{report['available_data_span_days']} days (required: 14)."
                        )

                reports_dir = Path(settings.governance_reports_dir)
                if not reports_dir.is_absolute():
                    from ..config.settings import ROOT_DIR
                    reports_dir = ROOT_DIR / reports_dir
                print(f"[OK] Saved structured report: {reports_dir / 'challenger_report_news_dedup.json'}")
                print(f"[OK] Saved human-readable summary: {reports_dir / 'challenger_report_news_dedup.md'}")

            elif args.command == "promote":
                from .rule_manager import RuleManager
                mgr = RuleManager()
                try:
                    await mgr.promote_rule(
                        rule_id=args.rule,
                        checklist_approved=args.checklist_approved,
                        reason=args.reason,
                    )
                    print(f"[OK] Rule '{args.rule}' successfully promoted to PRODUCTION.")
                    print("[OK] State transition logged to audit log.")
                except ValueError as e:
                    print(f"ERROR: {e}", file=sys.stderr)
                    sys.exit(1)
                except RuntimeError as e:
                    print(f"ERROR: Failed to persist promotion: {e}", file=sys.stderr)
                    sys.exit(1)

            elif args.command == "kill":
                from .rule_manager import RuleManager
                mgr = RuleManager()
                try:
                    await mgr.kill_rule(
                        rule_id=args.rule,
                        reason=args.reason,
                    )
                    print(f"[OK] Rule '{args.rule}' successfully DISABLED.")
                    print("[OK] Emergency rollback logged to audit trail.")
                except ValueError as e:
                    print(f"ERROR: {e}", file=sys.stderr)
                    sys.exit(1)
                except RuntimeError as e:
                    print(f"ERROR: Failed to persist kill-switch: {e}", file=sys.stderr)
                    sys.exit(1)

            elif args.command == "backfill":
                from ..services.backfill_service import BackfillService
                service = BackfillService()
                print(f"Starting historical situation taxonomy backfill job '{args.job_id}'...")
                try:
                    processed = await service.run_backfill(
                        job_id=args.job_id,
                        batch_size=args.batch_size,
                        delay_seconds=args.delay,
                        resume=args.resume
                    )
                except RuntimeError as e:
                    print(f"ERROR: {e}", file=sys.stderr)
                    sys.exit(1)
                except Exception as e:
                    print(f"ERROR: Backfill failed: {e}", file=sys.stderr)
                    sys.exit(1)
                progress = await service.get_job_progress(args.job_id)
                if progress is None:
                    print(
                        f"[WARN] Backfill finished processing {processed} records this run, "
                        f"but no progress row was found for job '{args.job_id}'.",
                        file=sys.stderr,
                    )
                elif progress.status == "COMPLETED":
                    print(
                        f"[OK] Historical backfill complete. "
                        f"status={progress.status} this_run={processed} "
                        f"processed_count={progress.processed_count}/{progress.total_count} "
                        f"last_processed_id={progress.last_processed_id}"
                    )
                else:
                    print(
                        f"[WARN] Historical backfill ended with status={progress.status}. "
                        f"this_run={processed} processed_count={progress.processed_count}/"
                        f"{progress.total_count} last_processed_id={progress.last_processed_id}. "
                        f"Re-run with --resume to continue.",
                        file=sys.stderr,
                    )

            elif args.command == "backfill-pause":
                from ..services.backfill_service import BackfillService
                service = BackfillService()
                try:
                    progress = await service.pause_backfill(args.job_id)
                except RuntimeError as e:
                    print(f"ERROR: {e}", file=sys.stderr)
                    sys.exit(1)
                print(
                    f"[OK] Backfill job '{args.job_id}' status={progress.status} "
                    f"last_processed_id={progress.last_processed_id} "
                    f"processed_count={progress.processed_count}/{progress.total_count}"
                )

            elif args.command == "taxonomy-report":
                from ..services.backfill_service import BackfillService
                service = BackfillService()
                output_path = await service.write_distribution_report(args.output_dir)
                print(f"[OK] Situation tag distribution report generated at {output_path}")

            elif args.command == "taxonomy-query":
                from ..services.analytics_service import AnalyticsService

                tags = [t.strip() for t in args.tags.split(",") if t.strip()]
                if not tags:
                    print("ERROR: --tags must include at least one tag", file=sys.stderr)
                    sys.exit(1)

                start_date = None
                end_date = None
                if args.start:
                    try:
                        start_date = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
                    except ValueError as e:
                        print(f"ERROR: Invalid --start datetime: {e}", file=sys.stderr)
                        sys.exit(1)
                if args.end:
                    try:
                        end_date = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
                    except ValueError as e:
                        print(f"ERROR: Invalid --end datetime: {e}", file=sys.stderr)
                        sys.exit(1)

                analytics = AnalyticsService()
                rows = await analytics.query_by_situation_tags(
                    db,
                    tags=tags,
                    recommendation=args.recommendation,
                    start_date=start_date,
                    end_date=end_date,
                    limit=args.limit,
                )
                print(
                    f"Matched {len(rows)} recommendation(s) "
                    f"(tags={tags}, recommendation={args.recommendation}, "
                    f"start={args.start}, end={args.end}, limit={args.limit})"
                )
                for rec in rows:
                    symbol = rec.stock.symbol if getattr(rec, "stock", None) else rec.stock_id
                    print(
                        f"  id={rec.id} symbol={symbol} action={rec.recommendation} "
                        f"tags={rec.situation_tags} created_at={rec.created_at}"
                    )


        except SingleActiveConstraintError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except TerminalStateError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except ExperimentNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except ExperimentError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def experiment_cli() -> None:
    args = _parse_args()
    if not args.command:
        print("Error: No command specified", file=sys.stderr)
        sys.exit(1)
    _require_taxonomy_admin(args)
    asyncio.run(_run_command(args))


if __name__ == "__main__":
    experiment_cli()
