# cli/main.py
import sys
from typing import Any
from importlib.metadata import version as _pkg_version, PackageNotFoundError
from pathlib import Path
import typer
from rich.console import Console

from cli.skill import skill_app

try:
    _VERSION = _pkg_version("hop-top-eva")
except PackageNotFoundError:
    _VERSION = "0.0.0"

app = typer.Typer()
console = Console()
app.add_typer(skill_app, name="skill")


def _version_callback(value: bool):
    if value:
        console.print(_VERSION)
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
):
    pass

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
    dataset: Path | None = typer.Option(None, "--dataset", help="Path to eval dataset (YAML or JSONL)"),
    target: str | None = typer.Option(None, "--target", help="Override target agent URL"),
    provider: str | None = typer.Option(
        None, "--provider", help="Chat target provider: openai | anthropic"
    ),
    base_url: str | None = typer.Option(
        None, "--base-url", help="Chat target base URL (e.g. http://localhost:12000/v1)"
    ),
    model: str | None = typer.Option(None, "--model", help="Chat target model id"),
    api_key_env: str | None = typer.Option(
        None, "--api-key-env", help="Env var NAME holding the chat target API key"
    ),
    max_tokens: int | None = typer.Option(None, "--max-tokens", help="Chat target max tokens"),
    temperature: float | None = typer.Option(None, "--temperature", help="Chat target temperature"),
    top_p: float | None = typer.Option(None, "--top-p", help="Chat target top_p"),
    timeout_s: float | None = typer.Option(
        None, "--timeout-s", help="Chat target request timeout (seconds)"
    ),
    target_id: str | None = typer.Option(
        None, "--target-id",
        help="Dataset mode: identity of the target in stored per-case results "
        "(default provider:model, or the URL).",
    ),
    concurrency: int = typer.Option(1, "--concurrency", help="Number of concurrent tests"),
    no_tui: bool = typer.Option(False, "--no-tui", help="Disable rich TUI (for CI)"),
    contract: Path | None = typer.Option(
        None, "--contract", help="Standalone mode: contract YAML to evaluate against --input"
    ),
    input_path: str | None = typer.Option(
        None, "--input", help="Standalone mode: input file (or '-' for stdin)"
    ),
    fmt: str | None = typer.Option(
        None,
        "--format",
        help="Output: 'text' (default) or 'json'. Dataset mode: 'json' dumps the Run (implies --no-tui).",
    ),
    quiet: bool = typer.Option(False, "--quiet", help="Standalone mode: suppress passing evaluator output"),
    prompt: str | None = typer.Option(
        None, "--prompt",
        help="Standalone mode: request prompt text for judge evaluators",
    ),
    prompt_file: str | None = typer.Option(
        None, "--prompt-file",
        help="Standalone mode: file with the request prompt ('-' for stdin; not with --input -)",
    ),
    since: str | None = typer.Option(
        None, "--since",
        help="Dataset mode: also report accuracy on cases whose metadata.added "
        "is on/after this ISO date (YYYY-MM-DD).",
    ),
):
    """Run evaluations.

    Two modes:
      * Dataset mode (default): `eva run --dataset suite.yaml --target <url>`
        — calls a live agent for each test case. Chat targets call an LLM
        API directly: `eva run --dataset suite.yaml --provider openai
        --base-url http://localhost:12000/v1 --model <id>` (or a `target:`
        mapping in the dataset; flags override its fields).
      * Standalone contract mode: `eva run --contract c.yaml --input data.json`
        — evaluates a single response artifact against a contract. No agent
        call, no gateway. Intended for CI smoke and local dev. Judge
        evaluators run when a judge is configured and `--prompt` /
        `--prompt-file` supplies the request prompt; otherwise skipped.
    """
    if (prompt is not None or prompt_file is not None) and (
        contract is None or input_path is None
    ):
        console.print(
            "[red]Error:[/red] --prompt/--prompt-file require --contract and --input"
        )
        raise typer.Exit(2)
    if prompt is not None and prompt_file is not None:
        console.print(
            "[red]Error:[/red] --prompt and --prompt-file are mutually exclusive"
        )
        raise typer.Exit(2)
    if prompt_file == "-" and input_path == "-":
        console.print(
            "[red]Error:[/red] --prompt-file - and --input - both read stdin; "
            "use a file for one"
        )
        raise typer.Exit(2)

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
        if since is not None:
            console.print("[red]Error:[/red] --since applies to dataset mode only")
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
            prompt=prompt,
            prompt_file=prompt_file,
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
    from core.config import find_and_load_config
    from core.dataset import load_dataset
    from core.evaluators.errors import EvaluatorConfigError
    from core.llm import build_llm_adapter
    from rich.markup import escape
    from core.loader import build_manager
    from core.runner import Runner
    from core.storage import SqliteStorage

    if fmt is not None and fmt not in ("json", "text"):
        console.print("[red]Error:[/red] --format must be 'json' or 'text'")
        raise typer.Exit(2)

    since_date = None
    if since is not None:
        from core.categories import parse_since

        try:
            since_date = parse_since(since)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(2)

    if target and not (target.startswith("http://") or target.startswith("https://")):
        console.print("[red]Error:[/red] --target must start with http:// or https://")
        raise typer.Exit(1)

    chat_flags = {
        "provider": provider, "base_url": base_url, "model": model,
        "api_key_env": api_key_env, "max_tokens": max_tokens,
        "temperature": temperature, "top_p": top_p, "timeout_s": timeout_s,
    }
    chat_flags = {k: v for k, v in chat_flags.items() if v is not None}
    if target and chat_flags:
        console.print(
            "[red]Error:[/red] --target (URL) cannot be combined with chat target flags"
        )
        raise typer.Exit(2)
    try:
        ds = load_dataset(
            dataset, target=target, chat=chat_flags or None, target_id=target_id
        )
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)
    if ds.append_only:
        from core.append_only import check as _check_append_only

        _res = _check_append_only(dataset)
        if not _res.ok:
            for _p in _res.problems:
                typer.echo(f"problem: {_p.message}", err=True)
            raise typer.Exit(3)
    pm = build_manager(plugin_file=Path("plugins.py"))
    # Judge adapter: EVA_JUDGE_MODEL env / eva.yaml judge.model. None is fine —
    # judge-based builtin refs then skip with a reason (surfaced below).
    try:
        llm_adapter = build_llm_adapter(find_and_load_config())
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)

    if ds.chat is not None:
        from core.chat_targets import build_provider

        chat_provider = build_provider(ds.chat)

        async def call_agent(
            input: str, target_url: str, tools: Any = None, tool_choice: Any = None
        ) -> Any:
            return await chat_provider.complete(
                input, tools=tools, tool_choice=tool_choice
            )
    else:

        async def call_agent(
            input: str, target_url: str, tools: Any = None, tool_choice: Any = None
        ) -> Any:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(target_url, json={"input": input})
                return resp.text

    storage = SqliteStorage()
    runner = Runner(
        pm=pm,
        call_agent=call_agent,
        concurrency=concurrency,
        llm_adapter=llm_adapter,
        storage=storage,
    )

    try:
        if fmt == "json":
            eva_run = asyncio.run(runner.execute(ds))
            if since_date is not None:
                from core.categories import since_score

                eva_run.since = since_score(eva_run.cases, since_date)
            print(eva_run.model_dump_json())
        else:
            if no_tui:
                eva_run = asyncio.run(runner.execute(ds))
                _print_plain(eva_run)
            else:
                eva_run = _run_with_tui(runner, ds)
            from core.categories import format_figures

            for line in format_figures(eva_run.cases, since_date):
                console.print(escape(line))
    except EvaluatorConfigError as e:
        # Raised while evaluators are resolved, before any target call.
        console.print(f"[red]Error:[/red] {escape(str(e))}")
        raise typer.Exit(2)

    if getattr(eva_run, "skipped", None):
        from rich.console import Console as _Console
        _err = _Console(stderr=True)
        for note in eva_run.skipped:
            _err.print(f"[yellow]skipped:[/yellow] {note}")

    storage.save_run(eva_run)

    raise typer.Exit(0 if eva_run.passed else 1)


def _print_plain(eva_run) -> None:
    """Plain-text result output (CI / --no-tui mode)."""
    from rich.markup import escape

    total = len(eva_run.results)
    passed = sum(1 for r in eva_run.results if r.passed)
    for r in eva_run.results:
        icon = "[green]✓[/green]" if r.passed else "[red]✗[/red]"
        why = f" — {r.score.reason}" if not r.passed and r.score.reason else ""
        console.print(
            f"  {icon} "
            + escape(f"{r.test_id} · {r.evaluator} ({r.duration_ms}ms){why}")
        )
    console.print(f"\nResults: {passed}/{total} Passed.  Run: {eva_run.run_id}")


def _run_with_tui(runner, ds):
    """Execute runner with rich progress spinner and results table."""
    import asyncio
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn,
    )
    from rich.markup import escape
    from rich.table import Table

    total_tests = len(ds.scored_tests())
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

        eva_run = asyncio.run(
            runner.execute(ds, on_test_done=lambda: progress.advance(ptask))
        )

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
            escape(r.score.reason or ""),
        )
    console.print(table)

    total = len(eva_run.results)
    n_passed = sum(1 for r in eva_run.results if r.passed)
    status = "[green]PASSED[/green]" if eva_run.passed else "[red]FAILED[/red]"
    console.print(
        f"\n{status}  {n_passed}/{total} passed  ({eva_run.duration_ms}ms)  "
        f"Run: {eva_run.run_id}"
    )
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
    no_auth: bool = typer.Option(
        False,
        "--no-auth",
        help="Serve without API-key authentication (required when no key store "
        "is configured via EVA_REDIS_URL)",
    ),
) -> None:
    """Start the Eva gateway server."""
    import os
    import uvicorn
    from cli.run_contract import EXIT_BAD_INPUT
    from core.config import find_and_load_config
    from core.llm import JudgeConfigError, build_llm_adapter

    # Fail at start, in every serve mode: a judge that cannot be built must not
    # surface per request (or per worker, after the port is bound). Checked
    # before importing server.app, whose module-level app reads the same config.
    try:
        judge_adapter = build_llm_adapter(find_and_load_config())
    except JudgeConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(EXIT_BAD_INPUT)

    from server.app import SERVE_CONTRACTS_DIR_ENV, create_app, create_serve_app
    from server.auth import NO_AUTH_ENV, AuthNotConfiguredError, serve_auth_mode
    from server.contracts.registry import ContractRegistry

    try:
        mode = serve_auth_mode(no_auth)
    except AuthNotConfiguredError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(EXIT_BAD_INPUT)

    # The app is built in this process (single worker) or in child processes
    # (workers > 1, reload); the env carries the choice to both. Set or clear
    # explicitly so an inherited value cannot disagree with the flag.
    if mode == "disabled":
        os.environ[NO_AUTH_ENV] = "1"
        typer.echo(
            "Warning: --no-auth: gateway is UNAUTHENTICATED; every route is "
            "open to anyone who can reach this port.",
            err=True,
        )
    else:
        os.environ.pop(NO_AUTH_ENV, None)

    registry = ContractRegistry()
    if contracts_dir.exists():
        registry.load_dir(contracts_dir)
        typer.echo(f"Loaded {len(registry.all())} contract(s) from {contracts_dir}")
    else:
        typer.echo(
            f"Warning: contracts directory '{contracts_dir}' not found — starting with empty registry"
        )

    if reload or workers > 1:
        # uvicorn requires an import string here; the app is built per process.
        os.environ[SERVE_CONTRACTS_DIR_ENV] = str(contracts_dir.resolve())
        uvicorn.run(
            "server.app:create_serve_app",
            factory=True,
            host=host,
            port=port,
            workers=workers if not reload else 1,
            reload=reload,
        )
        return

    uvicorn.run(
        create_app(registry=registry, judge_adapter=judge_adapter),
        host=host,
        port=port,
    )


annotate_app = typer.Typer(help="Annotation commands.")
app.add_typer(annotate_app, name="annotate")


@annotate_app.command("add")
def annotate_add(
    invocation: str = typer.Option(..., "--invocation", help="Invocation ID to annotate."),
    label: str | None = typer.Option(None, "--label", help="Human label (e.g. 'correct', 'wrong')."),
    score: float | None = typer.Option(None, "--score", help="Human quality score (0.0–1.0)."),
    notes: str | None = typer.Option(None, "--notes", help="Free-text notes."),
    reviewer: str = typer.Option("human", "--reviewer", help="Reviewer identifier."),
    db: str | None = typer.Option(None, "--db", help="Path to SQLite DB (overrides eva.yaml)."),
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
    db: str | None = typer.Option(None, "--db", help="Path to SQLite DB (overrides eva.yaml)."),
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
    db: str | None = typer.Option(None, "--db", help="Path to SQLite DB (overrides eva.yaml)."),
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


from cli.results_cmd import results_app

app.add_typer(results_app, name="results")

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

from cli.dataset_cmd import dataset_app

app.add_typer(dataset_app, name="dataset")

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
    db: str | None = typer.Option(None, help="Path to SQLite DB (overrides eva.yaml)."),
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


data_app = typer.Typer(help="Evaluator data commands.")
app.add_typer(data_app, name="data")


@data_app.command("fetch")
def data_fetch(
    directory: str | None = typer.Option(
        None, "--dir",
        help="Target directory (default: first NLTK_DATA entry, else "
        "$XDG_DATA_HOME/eva/nltk_data).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be fetched; no network, no writes."
    ),
    fmt: str | None = typer.Option(
        None, "--format", help="Output: 'text' (default in TTY) or 'json' (default otherwise)."
    ),
) -> None:
    """Fetch the nltk data the ifeval_check evaluator needs (one time).

    Exit codes: 0 ok (fetched or already present), 1 a download failed,
    2 invalid flag, 3 the 'ifeval' extra (nltk) is not installed.
    """
    import json

    chosen = fmt or ("json" if not sys.stdout.isatty() else "text")
    if chosen not in ("json", "text"):
        console.print("[red]Error:[/red] --format must be 'json' or 'text'")
        raise typer.Exit(2)

    from core import nltk_data

    if not dry_run:
        try:
            import nltk  # noqa: F401
        except ImportError:
            print(
                'Error: nltk not installed; run: pip install "hop-top-eva[ifeval]"',
                file=sys.stderr,
            )
            raise typer.Exit(3)

    result = nltk_data.fetch(directory=directory, dry_run=dry_run)
    if chosen == "json":
        print(json.dumps(result))
    else:
        for r in result["resources"]:
            print(f"{r['status']:<12} {r['id']}")
        print(f"dir: {result['dir']}")
    if not result["ok"]:
        print("Error: some downloads failed", file=sys.stderr)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
