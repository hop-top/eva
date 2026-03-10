import json
import typer
from pathlib import Path
from eva_mcp.importer import import_mcp_manifest, contracts_to_yaml, MCPImportError

app = typer.Typer()


@app.command()
def convert(
    manifest_file: Path = typer.Argument(..., help="Path to MCP server manifest JSON file"),
    output_dir: Path = typer.Option(Path("contracts"), help="Output directory for YAML contracts"),
) -> None:
    """Convert an MCP server manifest JSON to Eva contract YAML files."""
    if not manifest_file.exists():
        typer.echo(f"Error: file not found: {manifest_file}", err=True)
        raise typer.Exit(1)

    try:
        manifest = json.loads(manifest_file.read_text())
        contracts = import_mcp_manifest(manifest)
        paths = contracts_to_yaml(contracts, output_dir)
    except MCPImportError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Converted {len(paths)} contract(s) to {output_dir}/")
    for p in paths:
        typer.echo(f"  {p}")


if __name__ == "__main__":
    app()
