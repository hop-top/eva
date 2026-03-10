# cli/main.py
from pathlib import Path
import typer
from rich.console import Console

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
    console.print("0.1.0")


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
    dataset: Path = typer.Option(..., "--dataset", help="Path to eval dataset (YAML or JSONL)"),
    target: str = typer.Option(None, "--target", help="Override target agent URL"),
    concurrency: int = typer.Option(1, "--concurrency", help="Number of concurrent tests"),
    no_tui: bool = typer.Option(False, "--no-tui", help="Disable rich TUI (for CI)"),
):
    """Run evaluations against a target agent."""
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
