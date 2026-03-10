import json
import typer
from pathlib import Path
from eva_a2a.importer import import_agent_card, contracts_to_yaml, A2AImportError

app = typer.Typer()


@app.command()
def convert(
    card_file: Path = typer.Argument(..., help="Path to A2A Agent Card JSON file"),
    output_dir: Path = typer.Option(Path("contracts"), help="Output directory for YAML contracts"),
) -> None:
    """Convert an A2A Agent Card JSON file to Eva contract YAML files."""
    if not card_file.exists():
        typer.echo(f"Error: file not found: {card_file}", err=True)
        raise typer.Exit(1)

    try:
        card = json.loads(card_file.read_text())
        contracts = import_agent_card(card)
        paths = contracts_to_yaml(contracts, output_dir)
    except A2AImportError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Converted {len(paths)} contract(s) to {output_dir}/")
    for p in paths:
        typer.echo(f"  {p}")


if __name__ == "__main__":
    app()
