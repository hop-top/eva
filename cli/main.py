# cli/main.py
import sys
from importlib.metadata import version as _pkg_version, PackageNotFoundError
from pathlib import Path
import typer
from rich.console import Console

try:
    _VERSION = _pkg_version("eva")
except PackageNotFoundError:
    _VERSION = "0.0.0"

app = typer.Typer()
console = Console()

PLUGIN_TEMPLATE = '''\
from core.plugins import EvaPlugin, EvaSpec
from core.models import Score

# Example custom evaluator — delete or modify as needed.
# class MyCheck(EvaPlugin):
#     @EvaSpec.hook_impl
#     def run_eval(self, response: str, context: dict) -> Score:
#         return Score(value=1.0)
'''

ENV_TEMPLATE = '''\
EVA_STORAGE=sqlite:///.eva/state.db
EVA_JUDGE_MODEL=openai/gpt-4o-mini
# OPENAI_API_KEY=
'''


@app.command()
def version():
    """Show version."""
    console.print(_VERSION)


@app.command()
def init():
    """Scaffold Eva project structure in the current directory."""
    from core.config import _CONFIG_TEMPLATE, _CONFIG_FILENAME

    cwd = Path.cwd()

    evals_dir = cwd / "evals"
    evals_dir.mkdir(exist_ok=True)
    console.print(f"Created [green]{evals_dir.relative_to(cwd)}/[/green]")

    plugins_file = cwd / "plugins.py"
    if not plugins_file.exists():
        plugins_file.write_text(PLUGIN_TEMPLATE)
    console.print(f"Created [green]{plugins_file.name}[/green]")

    env_file = cwd / ".env"
    if not env_file.exists():
        env_file.write_text(ENV_TEMPLATE)
    console.print(f"Created [green]{env_file.name}[/green]")

    config_file = cwd / _CONFIG_FILENAME
    if not config_file.exists():
        config_file.write_text(_CONFIG_TEMPLATE)
    console.print(f"Created [green]{_CONFIG_FILENAME}[/green]")


contract_app = typer.Typer()
app.add_typer(contract_app, name="contract")


@contract_app.command("validate")
def contract_validate(path: Path = typer.Argument(..., help="Path to contract YAML file")):
    """Validate a contract YAML file."""
    from core.contract import load_contract, ContractValidationError
    try:
        contract = load_contract(path)
        console.print(f"[green]Valid[/green] contract: [bold]{contract.name}[/bold]")
        console.print(f"  Provider: {contract.provider}")
        console.print(f"  Evaluators: {len(contract.evaluators)}")
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except ContractValidationError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@contract_app.command("diff")
def contract_diff(
    contract_a: Path = typer.Argument(..., help="Path to base contract YAML"),
    contract_b: Path = typer.Argument(..., help="Path to new contract YAML"),
):
    """Detect regressions between two contract YAML versions."""
    from core.contract import load_contract, ContractValidationError
    from core.contract_diff import diff_contracts, format_diff_report

    try:
        a = load_contract(contract_a)
    except (FileNotFoundError, ContractValidationError) as e:
        console.print(f"[red]Error loading {contract_a}:[/red] {e}")
        raise typer.Exit(1)

    try:
        b = load_contract(contract_b)
    except (FileNotFoundError, ContractValidationError) as e:
        console.print(f"[red]Error loading {contract_b}:[/red] {e}")
        raise typer.Exit(1)

    report = diff_contracts(a, b)
    format_diff_report(console, contract_a, contract_b, report)

    if report.has_regressions:
        raise typer.Exit(1)


@app.command()
def run(
    dataset: Path = typer.Option(None, "--dataset", help="Path to eval dataset (YAML or JSONL)"),
    target: str = typer.Option(None, "--target", help="Override target agent URL"),
    concurrency: int = typer.Option(1, "--concurrency", help="Number of concurrent tests"),
    no_tui: bool = typer.Option(False, "--no-tui", help="Disable rich TUI (for CI)"),
    contract: Path = typer.Option(
        None, "--contract", help="Standalone mode: contract YAML to evaluate against --input"
    ),
    input_path: str = typer.Option(
        None, "--input", help="Standalone mode: input file (or '-' for stdin)"
    ),
    fmt: str = typer.Option(
        None, "--format", help="Standalone mode output: 'text' (default) or 'json' (CI default)"
    ),
    quiet: bool = typer.Option(False, "--quiet", help="Standalone mode: suppress passing evaluator output"),
):
    """Run evaluations.

    Two modes:
      * Dataset mode (default): `eva run --dataset suite.yaml --target <url>`
        — calls a live agent for each test case.
      * Standalone contract mode: `eva run --contract c.yaml --input data.json`
        — evaluates a single response artifact against a contract. No agent
        call, no gateway. Intended for CI smoke and local dev.
    """
    # Standalone contract mode dispatch
    if contract is not None or input_path is not None:
        if contract is None or input_path is None:
            console.print(
                "[red]Error:[/red] --contract and --input must be used together"
            )
            raise typer.Exit(2)
        if dataset is not None or target is not None:
            console.print(
                "[red]Error:[/red] --contract/--input cannot be combined with --dataset/--target"
            )
            raise typer.Exit(2)
        from cli.run_contract import run_contract_cli

        chosen_fmt = fmt or ("json" if not sys.stdout.isatty() else "text")
        if chosen_fmt not in ("json", "text"):
            console.print("[red]Error:[/red] --format must be 'json' or 'text'")
            raise typer.Exit(2)
        code = run_contract_cli(
            contract=contract,
            input_path=input_path,
            fmt=chosen_fmt,
            quiet=quiet,
        )
        raise typer.Exit(code)

    if dataset is None:
        console.print(
            "[red]Error:[/red] --dataset is required (dataset mode) "
            "or use --contract/--input for standalone mode"
        )
        raise typer.Exit(2)

    import asyncio
    import httpx
    from core.dataset import load_dataset
    from core.loader import build_manager
    from core.runner import Runner
    from core.storage import SqliteStorage

    if target and not (target.startswith("http://") or target.startswith("https://")):
        console.print("[red]Error:[/red] --target must start with http:// or https://")
        raise typer.Exit(1)

    ds = load_dataset(dataset, target=target)
    pm = build_manager(plugin_file=Path("plugins.py"))

    async def call_agent(input: str, target_url: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(target_url, json={"input": input})
            return resp.text

    runner = Runner(pm=pm, call_agent=call_agent, concurrency=concurrency)

    if no_tui:
        eva_run = asyncio.run(runner.execute(ds))
        _print_plain(eva_run)
    else:
        eva_run = _run_with_tui(runner, ds)

    storage = SqliteStorage()
    storage.save_run(eva_run)

    raise typer.Exit(0 if eva_run.passed else 1)


def _print_plain(eva_run) -> None:
    """Plain-text result output (CI / --no-tui mode)."""
    total = len(eva_run.results)
    passed = sum(1 for r in eva_run.results if r.passed)
    for r in eva_run.results:
        icon = "[green]✓[/green]" if r.passed else "[red]✗[/red]"
        console.print(f"  {icon} {r.test_id} ({r.duration_ms}ms)")
    console.print(f"\nResults: {passed}/{total} Passed.")


def _run_with_tui(runner, ds):
    """Execute runner with rich progress spinner and results table."""
    import asyncio
    import uuid
    from datetime import datetime
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn,
    )
    from rich.table import Table
    from core.models import Result, Run

    total_tests = len(ds.tests)
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )

    with progress:
        ptask = progress.add_task(
            f"[cyan]Evaluating {ds.name}[/cyan]", total=total_tests
        )

        async def _tracked():
            started_at = datetime.utcnow()
            run_id = str(uuid.uuid4())[:8]
            semaphore = asyncio.Semaphore(runner.max_workers)
            results = []

            async def run_one(test):
                async with semaphore:
                    t0 = datetime.utcnow()
                    runner.pm.hook.before_eval(test_id=test.id, context={})
                    response = await runner.call_agent(test.input, ds.target)
                    scores = runner.pm.hook.run_eval(
                        response=response,
                        context={"test": test.model_dump()},
                    )
                    t1 = datetime.utcnow()
                    ms = int((t1 - t0).total_seconds() * 1000)
                    batch = []
                    for score in scores:
                        r = Result(
                            test_id=test.id,
                            evaluator="unknown",
                            score=score,
                            mode="binary",
                            min_score=1.0,
                            duration_ms=ms,
                        )
                        runner.pm.hook.after_eval(
                            test_id=test.id, score=score, context={}
                        )
                        batch.append(r)
                    progress.advance(ptask)
                    return batch

            all_batches = await asyncio.gather(*[run_one(t) for t in ds.tests])
            for batch in all_batches:
                results.extend(batch)

            t_end = datetime.utcnow()
            ok = all(r.passed for r in results) if results else True
            return Run(
                run_id=run_id,
                dataset=ds.name,
                target=ds.target,
                results=results,
                started_at=started_at,
                duration_ms=int((t_end - started_at).total_seconds() * 1000),
                passed=ok,
            )

        eva_run = asyncio.run(_tracked())

    table = Table(title="Evaluation Results", show_lines=False)
    table.add_column("Sample", style="cyan")
    table.add_column("Evaluator", style="magenta")
    table.add_column("Score", justify="right")
    table.add_column("Pass", justify="center")
    table.add_column("Reason")
    for r in eva_run.results:
        table.add_row(
            r.test_id,
            r.evaluator,
            f"{r.score.value:.2f}",
            "[green]✓[/green]" if r.passed else "[red]✗[/red]",
            r.score.reason or "",
        )
    console.print(table)

    total = len(eva_run.results)
    n_passed = sum(1 for r in eva_run.results if r.passed)
    status = "[green]PASSED[/green]" if eva_run.passed else "[red]FAILED[/red]"
    console.print(f"\n{status}  {n_passed}/{total} passed  ({eva_run.duration_ms}ms)")
    return eva_run


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8080, help="Bind port"),
    contracts_dir: Path = typer.Option(
        Path("contracts"), help="Directory of contract YAML files to load"
    ),
    reload: bool = typer.Option(False, help="Enable hot-reload (dev mode)"),
    workers: int = typer.Option(1, help="Number of uvicorn workers"),
) -> None:
    """Start the Eva gateway server."""
    import uvicorn
    from server.app import create_app
    from server.contracts.registry import ContractRegistry

    registry = ContractRegistry()
    if contracts_dir.exists():
        registry.load_dir(contracts_dir)
        typer.echo(f"Loaded {len(registry.all())} contract(s) from {contracts_dir}")
    else:
        typer.echo(
            f"Warning: contracts directory '{contracts_dir}' not found — starting with empty registry"
        )

    _app = create_app(registry=registry)

    uvicorn.run(
        _app,
        host=host,
        port=port,
        workers=workers if not reload else 1,
        reload=reload,
    )


annotate_app = typer.Typer(help="Annotation commands.")
app.add_typer(annotate_app, name="annotate")


@annotate_app.command("add")
def annotate_add(
    invocation: str = typer.Option(..., "--invocation", help="Invocation ID to annotate."),
    label: str = typer.Option(None, "--label", help="Human label (e.g. 'correct', 'wrong')."),
    score: float = typer.Option(None, "--score", help="Human quality score (0.0–1.0)."),
    notes: str = typer.Option(None, "--notes", help="Free-text notes."),
    reviewer: str = typer.Option("human", "--reviewer", help="Reviewer identifier."),
    db: str = typer.Option(None, "--db", help="Path to SQLite DB (overrides eva.yaml)."),
) -> None:
    """Add a human annotation to an invocation."""
    import uuid
    from datetime import datetime, timezone
    from core.models import Annotation
    from core.storage import SqliteStorage

    db_url = f"sqlite:///{db}" if db else "sqlite:///.eva/state.db"
    storage = SqliteStorage(db_url=db_url)

    annotation = Annotation(
        annotation_id=str(uuid.uuid4()),
        invocation_id=invocation,
        reviewer=reviewer,
        label=label,
        score=score,
        notes=notes,
        created_at=datetime.now(tz=timezone.utc),
    )
    storage.save_annotation(annotation)
    console.print(
        f"[green]Annotation saved[/green] [dim]{annotation.annotation_id}[/dim]"
        f" → invocation [bold]{invocation}[/bold]"
    )


@annotate_app.command("list")
def annotate_list(
    invocation: str = typer.Option(..., "--invocation", help="Invocation ID."),
    db: str = typer.Option(None, "--db", help="Path to SQLite DB (overrides eva.yaml)."),
) -> None:
    """List annotations for an invocation."""
    from rich.table import Table
    from core.storage import SqliteStorage

    db_url = f"sqlite:///{db}" if db else "sqlite:///.eva/state.db"
    storage = SqliteStorage(db_url=db_url)

    annotations = storage.list_annotations(invocation)
    if not annotations:
        console.print(f"[yellow]No annotations for invocation {invocation}[/yellow]")
        return

    table = Table(title=f"Annotations — {invocation}")
    table.add_column("ID", style="dim")
    table.add_column("Reviewer")
    table.add_column("Label")
    table.add_column("Score", justify="right")
    table.add_column("Notes")
    table.add_column("Created")

    for ann in annotations:
        table.add_row(
            ann.annotation_id[:8] + "…",
            ann.reviewer,
            ann.label or "—",
            f"{ann.score:.2f}" if ann.score is not None else "—",
            ann.notes or "—",
            ann.created_at.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


review_app = typer.Typer(help="Human review commands.")
app.add_typer(review_app, name="review")


@review_app.command("queue")
def review_queue_cmd(
    failed_only: bool = typer.Option(
        False, "--failed-only", help="Show only invocations with failed evaluators."
    ),
    db: str = typer.Option(None, "--db", help="Path to SQLite DB (overrides eva.yaml)."),
) -> None:
    """Show invocations pending human review."""
    from rich.table import Table
    from core.storage import SqliteStorage
    from core.query import review_queue

    db_url = f"sqlite:///{db}" if db else "sqlite:///.eva/state.db"
    storage = SqliteStorage(db_url=db_url)

    items = review_queue(storage, failed_only=failed_only)
    if not items:
        console.print("[green]Review queue is empty.[/green]")
        return

    table = Table(title="Review Queue")
    table.add_column("Invocation", style="cyan")
    table.add_column("Status")
    table.add_column("Target")
    table.add_column("Evaluator Scores")
    table.add_column("Human Label")
    table.add_column("Flags")

    for item in items:
        inv = item["invocation"]
        er_list = item["evaluator_results"]
        ann_list = item["annotations"]
        has_failure = item["has_failure"]
        needs_review = item["needs_review"]

        # Evaluator scores summary: "name: 0.75 (pass)" per result
        ev_parts = []
        for er in er_list:
            state = "pass" if er.passed else "fail"
            score_str = f"{er.score_value:.2f}" if er.score_value is not None else "—"
            ev_parts.append(f"{er.evaluator}: {score_str} ({state})")
        ev_summary = "; ".join(ev_parts) if ev_parts else "—"

        # Human label from most recent annotation
        human_label = "—"
        if ann_list:
            latest = sorted(ann_list, key=lambda a: a.created_at)[-1]
            parts = []
            if latest.label:
                parts.append(latest.label)
            if latest.score is not None:
                parts.append(f"score={latest.score:.2f}")
            human_label = " ".join(parts) or "—"

        flags = []
        if has_failure:
            flags.append("[red]FAIL[/red]")
        if needs_review:
            flags.append("[yellow]UNREVIEWED[/yellow]")

        table.add_row(
            inv.invocation_id[:12] + "…",
            inv.status,
            inv.target[:30] + ("…" if len(inv.target) > 30 else ""),
            ev_summary,
            human_label,
            " ".join(flags) if flags else "[green]ok[/green]",
        )

    console.print(table)
    console.print(f"\n[dim]{len(items)} item(s) in queue[/dim]")


from cli.observe import (
    runs_app,
    invocations_app,
    compare_app,
    failures_app,
    usage_app,
)

app.add_typer(runs_app, name="runs")
app.add_typer(invocations_app, name="invocations")
app.add_typer(compare_app, name="compare")
app.add_typer(failures_app, name="failures")
app.add_typer(usage_app, name="usage")

drift_app = typer.Typer(help="Drift detection commands.")
app.add_typer(drift_app, name="drift")


@drift_app.command("report")
def drift_report(
    dataset: str = typer.Option(..., help="Dataset name to analyse."),
    target: str = typer.Option(..., help="Target agent URL."),
    window: int = typer.Option(10, help="Number of recent runs to compare."),
    threshold: float = typer.Option(
        0.1, help="Score delta that triggers DOWN/UP trend."
    ),
    db: str = typer.Option(None, help="Path to SQLite DB (overrides eva.yaml)."),
) -> None:
    """Show evaluator score trends across recent runs for a dataset+target pair."""
    import asyncio
    from rich.table import Table
    from core.drift import compute_drift, DriftTrend
    from core.storage import SqliteStorage

    db_url = f"sqlite:///{db}" if db else "sqlite:///.eva/state.db"
    storage = SqliteStorage(db_url=db_url)
    runs = asyncio.run(storage.get_runs(dataset=dataset, target=target, limit=window))

    if not runs:
        console.print(
            f"[yellow]No runs found for dataset=[bold]{dataset}[/bold] "
            f"target=[bold]{target}[/bold][/yellow]"
        )
        raise typer.Exit(0)

    report = compute_drift(runs, threshold=threshold)

    table = Table(
        title=f"Drift Report — {dataset} → {target} (last {len(runs)} runs)"
    )
    table.add_column("Evaluator", style="cyan", no_wrap=True)
    table.add_column("Baseline", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Trend", justify="center")

    trend_styles = {
        DriftTrend.UP: "[green]↑ up[/green]",
        DriftTrend.DOWN: "[red]↓ down[/red]",
        DriftTrend.STABLE: "[dim]— stable[/dim]",
    }

    for entry in report.entries:
        baseline_str = (
            f"{entry.baseline_score:.4f}" if entry.baseline_score is not None else "—"
        )
        delta_str = f"{entry.delta:+.4f}" if entry.delta is not None else "—"
        table.add_row(
            entry.evaluator,
            baseline_str,
            f"{entry.current_score:.4f}",
            delta_str,
            trend_styles[entry.trend],
        )

    console.print(table)


if __name__ == "__main__":
    app()
