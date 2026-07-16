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
    asyncio.run(_run_command(args))


if __name__ == "__main__":
    experiment_cli()
