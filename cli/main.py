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


@app.command()
def run(
    dataset: Path = typer.Option(..., "--dataset", help="Path to eval dataset (YAML or JSONL)"),
    target: str = typer.Option(None, "--target", help="Override target agent URL"),
    concurrency: int = typer.Option(1, "--concurrency", help="Number of concurrent tests"),
):
    """Run evaluations against a target agent."""
    import asyncio
    import httpx
    from core.dataset import load_dataset
    from core.loader import build_manager
    from core.runner import Runner
    from core.storage import SqliteStorage

    ds = load_dataset(dataset, target=target)
    # Load user plugins if they exist
    pm = build_manager(plugin_file=Path("plugins.py"))

    async def call_agent(input: str, target_url: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(target_url, json={"input": input})
            return resp.text

    runner = Runner(pm=pm, call_agent=call_agent, concurrency=concurrency)
    eva_run = asyncio.run(runner.execute(ds))

    # Basic output
    total = len(eva_run.results)
    passed = sum(1 for r in eva_run.results if r.passed)
    for r in eva_run.results:
        icon = "[green]✓[/green]" if r.passed else "[red]✗[/red]"
        console.print(f"  {icon} {r.test_id} ({r.duration_ms}ms)")

    console.print(f"\nResults: {passed}/{total} Passed.")

    # In Phase 1, we just use default storage. In Phase 2+ we'll use EVA_STORAGE env.
    storage = SqliteStorage()
    storage.save_run(eva_run)

    raise typer.Exit(0 if eva_run.passed else 1)


if __name__ == "__main__":
    app()
