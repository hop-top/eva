# cli/observe.py
"""Observability CLI commands: runs, invocations, compare, failures, usage."""
from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# Sub-apps
# ---------------------------------------------------------------------------

runs_app = typer.Typer(help="Query stored eval runs.")
invocations_app = typer.Typer(help="Query individual invocations.")
failures_app = typer.Typer(help="Inspect failed evaluations.")
usage_app = typer.Typer(help="Token and cost usage reports.")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NA = "[dim]—[/dim]"


def _fmt_opt(v, fmt: str = "{}") -> str:
    return fmt.format(v) if v is not None else _NA


def _storage(db: Optional[str] = None):
    from core.storage import SqliteStorage
    db_url = f"sqlite:///{db}" if db else "sqlite:///.eva/state.db"
    return SqliteStorage(db_url=db_url)


# ---------------------------------------------------------------------------
# eva runs list
# ---------------------------------------------------------------------------

@runs_app.command("list")
def runs_list(
    dataset: Optional[str] = typer.Option(None, "--dataset", help="Filter by dataset name."),
    target: Optional[str] = typer.Option(None, "--target", help="Filter by target URL."),
    status: Optional[str] = typer.Option(
        None, "--status", help="Filter by status: pass | fail."
    ),
    limit: int = typer.Option(50, "--limit", help="Max rows to return."),
    db: Optional[str] = typer.Option(None, "--db", help="Path to SQLite DB file."),
) -> None:
    """List evaluation runs."""
    from core.query import list_runs

    storage = _storage(db)
    runs = list_runs(storage, dataset=dataset, target=target, status=status, limit=limit)

    if not runs:
        console.print("[yellow]No runs found.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Runs", show_lines=False)
    table.add_column("Run ID", style="cyan", no_wrap=True)
    table.add_column("Dataset")
    table.add_column("Target")
    table.add_column("Status", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Started At")

    for r in runs:
        # Compute aggregate pass rate from results if present
        if r.results:
            n_pass = sum(1 for x in r.results if x.passed)
            score_str = f"{n_pass}/{len(r.results)}"
        else:
            score_str = _NA
        status_str = "[green]pass[/green]" if r.passed else "[red]fail[/red]"
        started = r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at else _NA
        table.add_row(r.run_id, r.dataset, r.target, status_str, score_str, started)

    console.print(table)


# ---------------------------------------------------------------------------
# eva runs show
# ---------------------------------------------------------------------------

@runs_app.command("show")
def runs_show(
    run_id: str = typer.Option(..., "--run-id", help="Run ID to inspect."),
    db: Optional[str] = typer.Option(None, "--db", help="Path to SQLite DB file."),
) -> None:
    """Show run details and its invocations."""
    from core.query import list_runs, list_invocations

    storage = _storage(db)
    runs = list_runs(storage, limit=1000)
    run = next((r for r in runs if r.run_id == run_id), None)

    if run is None:
        console.print(f"[red]Run not found:[/red] {run_id}")
        raise typer.Exit(1)

    # Run summary
    started = run.started_at.strftime("%Y-%m-%d %H:%M:%S") if run.started_at else _NA
    status_str = "[green]pass[/green]" if run.passed else "[red]fail[/red]"
    console.print(f"[bold]Run:[/bold] {run.run_id}")
    console.print(f"  Dataset:    {run.dataset}")
    console.print(f"  Target:     {run.target}")
    console.print(f"  Status:     {status_str}")
    console.print(f"  Started at: {started}")
    console.print(f"  Duration:   {run.duration_ms}ms")

    # Invocations in this run
    invocations = list_invocations(storage, run_id=run_id, limit=500)

    if not invocations:
        console.print("\n[dim]No invocations recorded for this run.[/dim]")
        return

    table = Table(title=f"Invocations ({len(invocations)})", show_lines=False)
    table.add_column("Invocation ID", style="cyan", no_wrap=True)
    table.add_column("Test ID")
    table.add_column("Model")
    table.add_column("Status", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Contract")

    for inv in invocations:
        status_cell = _status_cell(inv.status)
        dur = f"{inv.duration_ms}ms" if inv.duration_ms is not None else _NA
        table.add_row(
            inv.invocation_id,
            _fmt_opt(inv.test_id),
            _fmt_opt(inv.model),
            status_cell,
            dur,
            _fmt_opt(inv.contract_name),
        )

    console.print(table)


def _status_cell(status: Optional[str]) -> str:
    if status == "pass":
        return "[green]pass[/green]"
    if status == "fail":
        return "[red]fail[/red]"
    if status == "upstream_error":
        return "[yellow]upstream_error[/yellow]"
    if status == "request_invalid":
        return "[yellow]request_invalid[/yellow]"
    return _fmt_opt(status)


# ---------------------------------------------------------------------------
# eva invocations show
# ---------------------------------------------------------------------------

@invocations_app.command("show")
def invocations_show(
    invocation_id: str = typer.Option(..., "--id", help="Invocation ID to inspect."),
    db: Optional[str] = typer.Option(None, "--db", help="Path to SQLite DB file."),
) -> None:
    """Show full detail for a single invocation."""
    from core.query import get_invocation_detail

    storage = _storage(db)
    detail = get_invocation_detail(storage, invocation_id)

    if not detail:
        console.print(f"[red]Invocation not found:[/red] {invocation_id}")
        raise typer.Exit(1)

    inv = detail["invocation"]
    started = inv.started_at.strftime("%Y-%m-%d %H:%M:%S") if inv.started_at else _NA
    console.print(f"[bold]Invocation:[/bold] {inv.invocation_id}")
    console.print(f"  Run ID:       {_fmt_opt(inv.run_id)}")
    console.print(f"  Source:       {inv.source}")
    console.print(f"  Dataset:      {_fmt_opt(inv.dataset)}")
    console.print(f"  Test ID:      {_fmt_opt(inv.test_id)}")
    console.print(f"  Target:       {inv.target}")
    console.print(f"  Provider:     {_fmt_opt(inv.provider)}")
    console.print(f"  Model:        {_fmt_opt(inv.model)}")
    console.print(f"  Contract:     {_fmt_opt(inv.contract_name)}")
    console.print(f"  Status:       {_status_cell(inv.status)}")
    console.print(f"  Started at:   {started}")
    console.print(f"  Duration:     {_fmt_opt(inv.duration_ms, '{}ms')}")
    console.print(f"  Request ID:   {_fmt_opt(inv.request_id)}")
    console.print(f"  Trace ID:     {_fmt_opt(inv.trace_id)}")

    # Artifacts (request / response content)
    artifacts = {a.artifact_id: a for a in detail.get("artifacts", [])}

    def _print_artifact(label: str, artifact_id: Optional[str]) -> None:
        if not artifact_id or artifact_id not in artifacts:
            return
        art = artifacts[artifact_id]
        console.print(f"\n[bold]{label}[/bold] ({art.content_type})")
        if art.redacted:
            console.print("  [dim](redacted)[/dim]")
        elif art.text_content:
            console.print(f"  {art.text_content[:500]}")
        elif art.json_content:
            console.print(f"  {art.json_content[:500]}")
        else:
            console.print(f"  [dim]blob: {_fmt_opt(art.blob_path)}[/dim]")

    _print_artifact("Request", inv.request_artifact_id)
    _print_artifact("Response", inv.response_artifact_id)

    # Evaluator results
    er_list = detail.get("evaluator_results", [])
    if er_list:
        er_table = Table(title="Evaluator Results", show_lines=False)
        er_table.add_column("Evaluator", style="magenta")
        er_table.add_column("Mode")
        er_table.add_column("Score", justify="right")
        er_table.add_column("Pass", justify="center")
        er_table.add_column("Reason")
        for er in er_list:
            pass_cell = "[green]✓[/green]" if er.passed else "[red]✗[/red]"
            er_table.add_row(
                er.evaluator,
                er.mode or _NA,
                f"{er.score_value:.4f}" if er.score_value is not None else _NA,
                pass_cell,
                er.reason or "",
            )
        console.print(er_table)

    # Tool calls
    tc_list = detail.get("tool_calls", [])
    if tc_list:
        tc_table = Table(title="Tool Calls", show_lines=False)
        tc_table.add_column("#", justify="right")
        tc_table.add_column("Tool", style="cyan")
        tc_table.add_column("Status", justify="center")
        tc_table.add_column("Duration", justify="right")
        tc_table.add_column("Error")
        for tc in tc_list:
            dur = f"{tc.duration_ms}ms" if tc.duration_ms is not None else _NA
            tc_table.add_row(
                str(tc.step_index),
                tc.tool_name,
                _status_cell(tc.status),
                dur,
                tc.error_text or "",
            )
        console.print(tc_table)

    # Usage records
    ur_list = detail.get("usage_records", [])
    if ur_list:
        ur_table = Table(title="Usage", show_lines=False)
        ur_table.add_column("Scope")
        ur_table.add_column("Model")
        ur_table.add_column("Prompt", justify="right")
        ur_table.add_column("Completion", justify="right")
        ur_table.add_column("Total", justify="right")
        ur_table.add_column("Cost (USD)", justify="right")
        for ur in ur_list:
            cost = f"${ur.estimated_cost_usd:.6f}" if ur.estimated_cost_usd is not None else _NA
            ur_table.add_row(
                ur.scope or _NA,
                ur.model or _NA,
                str(ur.prompt_tokens or 0),
                str(ur.completion_tokens or 0),
                str(ur.total_tokens or 0),
                cost,
            )
        console.print(ur_table)


# ---------------------------------------------------------------------------
# eva compare
# ---------------------------------------------------------------------------

compare_app = typer.Typer(help="Compare two runs side-by-side.")


@compare_app.callback(invoke_without_command=True)
def compare(
    left: str = typer.Option(..., "--left", help="Left (baseline) run ID."),
    right: str = typer.Option(..., "--right", help="Right (new) run ID."),
    db: Optional[str] = typer.Option(None, "--db", help="Path to SQLite DB file."),
) -> None:
    """Side-by-side diff of two runs: model, pass rate, cost, latency."""
    from core.query import compare_runs

    storage = _storage(db)
    result = compare_runs(storage, left, right)

    if "error" in result:
        console.print(f"[red]Error:[/red] {result['error']}")
        raise typer.Exit(1)

    lr = result["left"]
    rr = result["right"]
    ls = result["left_stats"]
    rs = result["right_stats"]

    # Summary header
    console.print(f"\n[bold]Compare:[/bold] [cyan]{lr.run_id}[/cyan]  vs  [cyan]{rr.run_id}[/cyan]")

    summary = Table(show_header=True, show_lines=False, title="Summary")
    summary.add_column("Metric")
    summary.add_column("Left", justify="right")
    summary.add_column("Right", justify="right")
    summary.add_column("Diff", justify="right")

    # Models
    l_models = ", ".join(sorted(ls["models"].keys())) or _NA
    r_models = ", ".join(sorted(rs["models"].keys())) or _NA
    summary.add_row("Model(s)", l_models, r_models, "")

    # Invocations
    summary.add_row(
        "Invocations",
        str(ls["invocation_count"]),
        str(rs["invocation_count"]),
        _diff_int(ls["invocation_count"], rs["invocation_count"]),
    )

    # Total cost
    cost_diff = result["cost_diff_usd"]
    cost_diff_str = _colorize_diff(f"${cost_diff:+.6f}", cost_diff, lower_is_better=True)
    summary.add_row(
        "Total cost (USD)",
        f"${ls['total_cost_usd']:.6f}",
        f"${rs['total_cost_usd']:.6f}",
        cost_diff_str,
    )

    console.print(summary)

    # Per-evaluator pass rate
    ev_diffs = result["evaluator_diffs"]
    if ev_diffs:
        ev_table = Table(title="Per-Evaluator Pass Rate", show_lines=False)
        ev_table.add_column("Evaluator", style="magenta")
        ev_table.add_column("Left %", justify="right")
        ev_table.add_column("Right %", justify="right")
        ev_table.add_column("Diff", justify="right")

        for ev, d in sorted(ev_diffs.items()):
            l_pr = d["left_pass_rate"]
            r_pr = d["right_pass_rate"]
            pr_diff = d["pass_rate_diff"]

            l_str = f"{l_pr*100:.1f}%" if l_pr is not None else _NA
            r_str = f"{r_pr*100:.1f}%" if r_pr is not None else _NA
            diff_str = (
                _colorize_diff(f"{pr_diff*100:+.1f}%", pr_diff, lower_is_better=False)
                if pr_diff is not None else _NA
            )
            ev_table.add_row(ev, l_str, r_str, diff_str)

        console.print(ev_table)


def _diff_int(a: int, b: int) -> str:
    d = b - a
    return f"{d:+d}"


def _colorize_diff(text: str, val: float, lower_is_better: bool) -> str:
    if val > 0:
        color = "red" if lower_is_better else "green"
    elif val < 0:
        color = "green" if lower_is_better else "red"
    else:
        return f"[dim]{text}[/dim]"
    return f"[{color}]{text}[/{color}]"


# ---------------------------------------------------------------------------
# eva failures list
# ---------------------------------------------------------------------------

@failures_app.command("list")
def failures_list(
    evaluator: Optional[str] = typer.Option(None, "--evaluator", help="Filter by evaluator name."),
    model: Optional[str] = typer.Option(None, "--model", help="Filter by model."),
    contract: Optional[str] = typer.Option(None, "--contract", help="Filter by contract name."),
    dataset: Optional[str] = typer.Option(None, "--dataset", help="Filter by dataset."),
    limit: int = typer.Option(50, "--limit", help="Max rows."),
    db: Optional[str] = typer.Option(None, "--db", help="Path to SQLite DB file."),
) -> None:
    """List failed invocations with failure reason."""
    from core.query import list_failures

    storage = _storage(db)
    failures = list_failures(
        storage,
        evaluator=evaluator,
        model=model,
        contract_name=contract,
        dataset=dataset,
        limit=limit,
    )

    if not failures:
        console.print("[green]No failures found.[/green]")
        raise typer.Exit(0)

    table = Table(title=f"Failures ({len(failures)})", show_lines=False)
    table.add_column("Invocation ID", style="cyan", no_wrap=True)
    table.add_column("Dataset")
    table.add_column("Model")
    table.add_column("Evaluator", style="magenta")
    table.add_column("Score", justify="right")
    table.add_column("Reason")

    for row in failures:
        inv = row["invocation"]
        er = row["evaluator_result"]
        inv_id = inv.invocation_id if inv else _NA
        ds = _fmt_opt(inv.dataset if inv else None)
        mdl = _fmt_opt(inv.model if inv else None)
        score = f"{er.score_value:.4f}" if er.score_value is not None else _NA
        table.add_row(inv_id, ds, mdl, er.evaluator, score, er.reason or "")

    console.print(table)


# ---------------------------------------------------------------------------
# eva usage report
# ---------------------------------------------------------------------------

@usage_app.command("report")
def usage_report(
    dataset: Optional[str] = typer.Option(None, "--dataset", help="Filter by dataset."),
    target: Optional[str] = typer.Option(None, "--target", help="Filter by target URL."),
    db: Optional[str] = typer.Option(None, "--db", help="Path to SQLite DB file."),
) -> None:
    """Token totals and cost breakdown by model."""
    from core.query import usage_report as q_usage_report

    storage = _storage(db)
    report = q_usage_report(storage, dataset=dataset, target=target)

    totals = report["totals"]
    by_model = report["by_model"]
    inv_count = report["invocation_count"]

    console.print(f"\n[bold]Usage Report[/bold]  ({inv_count} invocations)")
    if dataset:
        console.print(f"  Dataset: {dataset}")
    if target:
        console.print(f"  Target:  {target}")

    # Totals summary
    console.print(f"\n  Prompt tokens:     {int(totals['prompt_tokens']):>12,}")
    console.print(f"  Completion tokens: {int(totals['completion_tokens']):>12,}")
    console.print(f"  Total tokens:      {int(totals['total_tokens']):>12,}")
    console.print(f"  Est. cost (USD):   ${totals['estimated_cost_usd']:>12.6f}")

    if by_model:
        model_table = Table(title="Breakdown by Model", show_lines=False)
        model_table.add_column("Model", style="cyan")
        model_table.add_column("Prompt", justify="right")
        model_table.add_column("Completion", justify="right")
        model_table.add_column("Total", justify="right")
        model_table.add_column("Cost (USD)", justify="right")

        for mdl, stats in sorted(by_model.items()):
            model_table.add_row(
                mdl or _NA,
                f"{int(stats['prompt_tokens']):,}",
                f"{int(stats['completion_tokens']):,}",
                f"{int(stats['total_tokens']):,}",
                f"${stats['estimated_cost_usd']:.6f}",
            )

        console.print(model_table)
