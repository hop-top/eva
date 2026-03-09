# core/contract_diff.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from core.models import Contract


@dataclass
class EvaluatorChange:
    name: str
    kind: str          # "added" | "removed" | "threshold_raised" | "threshold_lowered"
    old_min_score: float | None = None
    new_min_score: float | None = None


@dataclass
class DiffReport:
    changes: list[EvaluatorChange] = field(default_factory=list)

    @property
    def has_regressions(self) -> bool:
        """Regressions = removed evaluators or lowered thresholds."""
        for c in self.changes:
            if c.kind in ("removed", "threshold_lowered"):
                return True
        return False


def diff_contracts(a: Contract, b: Contract) -> DiffReport:
    """Compare two contracts; return a DiffReport."""
    a_map = {e.name: e for e in a.evaluators}
    b_map = {e.name: e for e in b.evaluators}
    changes: list[EvaluatorChange] = []

    for name in a_map:
        if name not in b_map:
            changes.append(EvaluatorChange(name=name, kind="removed"))
        else:
            old_min = a_map[name].min_score
            new_min = b_map[name].min_score
            if new_min > old_min:
                changes.append(EvaluatorChange(
                    name=name, kind="threshold_raised",
                    old_min_score=old_min, new_min_score=new_min,
                ))
            elif new_min < old_min:
                changes.append(EvaluatorChange(
                    name=name, kind="threshold_lowered",
                    old_min_score=old_min, new_min_score=new_min,
                ))

    for name in b_map:
        if name not in a_map:
            changes.append(EvaluatorChange(name=name, kind="added"))

    return DiffReport(changes=changes)


def format_diff_report(
    console,
    path_a: Path,
    path_b: Path,
    report: DiffReport,
) -> None:
    """Print a colored diff report to the given rich Console."""
    console.print(
        f"\n[bold]Contract diff:[/bold] {path_a.name} → {path_b.name}\n"
    )
    if not report.changes:
        console.print("[green]No changes detected.[/green]")
        return

    for c in report.changes:
        if c.kind == "removed":
            console.print(f"  [red]− removed   [/red] {c.name}")
        elif c.kind == "added":
            console.print(f"  [green]+ added    [/green] {c.name}")
        elif c.kind == "threshold_raised":
            console.print(
                f"  [yellow]↑ tightened[/yellow] {c.name}  "
                f"min_score {c.old_min_score:.2f} → {c.new_min_score:.2f}"
            )
        elif c.kind == "threshold_lowered":
            console.print(
                f"  [red]↓ loosened [/red] {c.name}  "
                f"min_score {c.old_min_score:.2f} → {c.new_min_score:.2f}"
            )

    if report.has_regressions:
        console.print("\n[bold red]Regressions detected.[/bold red]")
    else:
        console.print("\n[bold green]No regressions.[/bold green]")
