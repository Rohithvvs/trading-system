# CLI Contracts: Experiment Governance

## Commands

All commands are run via `python -m app.governance.experiment_cli <command>` or registered as console_scripts.

### experiment start

Start a new experiment.

```
experiment start --name "<name>" [--metadata '{"key":"val"}']
```

**Success Output:**
```
Experiment 'test-exp' started (ID: uuid-here)
```

**Error - Already Active:**
```
Error: An experiment is already active (ID: uuid-here, name: 'other-exp'). Complete it first.
```

### experiment pause

Pause an active experiment.

```
experiment pause [--id <uuid>]
```

If `--id` is omitted, pauses the currently active experiment.

### experiment resume

Resume a paused experiment.

```
experiment resume [--id <uuid>]
```

### experiment complete

Complete an active/paused experiment.

```
experiment complete [--id <uuid>]
```

**Success Output:**
```
Experiment 'test-exp' completed. Duration: 45m 32s.
```

### experiment list

List experiments with optional filters.

```
experiment list [--status active|completed|failed] [--since <iso-date>] [--name <pattern>] [--limit 20] [--offset 0]
```

**Output:**
```
  ID                                    Name          Status       Started              Duration
  ────────────────────────────────────  ────────────  ───────────  ───────────────────  ────────
  uuid-here                             test-exp      active       2026-07-16 10:00:00  12m 34s
```

### experiment show

Show details of a specific experiment.

```
experiment show <uuid>
```

**Output:**
```
Experiment: test-exp (uuid-here)
Status: active  |  Started: 2026-07-16 10:00:00  |  Duration: 12m 34s
Metrics:
  avg_cpu: 45.2%
  avg_memory: 1024MB
```

### experiment metric

Add a metric observation to the active experiment.

```
experiment metric --name cpu_usage --value 45.2 [--unit %] [--tags '{"core":"0"}']
```

### audit trail

Export audit trail.

```
audit export --format json|csv --since <iso-date> --until <iso-date> [--output <file>]
```

If `--output` is omitted, writes to stdout.
