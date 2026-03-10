"""Tests that validate the structure and correctness of action.yml."""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
ACTION_FILE = REPO_ROOT / "action.yml"

REQUIRED_TOP_LEVEL_KEYS = {"name", "description", "inputs", "outputs", "runs"}

EXPECTED_INPUTS = {
    "contracts-dir",
    "dataset",
    "eva-version",
    "python-version",
    "fail-on-violation",
    "no-tui",
    "extra-args",
}

EXPECTED_OUTPUTS = {"violations", "result"}


@pytest.fixture(scope="module")
def action() -> dict:
    """Load and return the parsed action.yml."""
    assert ACTION_FILE.exists(), f"action.yml not found at {ACTION_FILE}"
    with ACTION_FILE.open() as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict), "action.yml must parse to a mapping"
    return data


def test_required_top_level_keys(action: dict) -> None:
    missing = REQUIRED_TOP_LEVEL_KEYS - action.keys()
    assert not missing, f"action.yml is missing top-level keys: {missing}"


def test_name_and_description_are_strings(action: dict) -> None:
    assert isinstance(action["name"], str) and action["name"].strip()
    assert isinstance(action["description"], str) and action["description"].strip()


def test_runs_using_composite(action: dict) -> None:
    runs = action["runs"]
    assert isinstance(runs, dict), "'runs' must be a mapping"
    assert runs.get("using") == "composite", (
        f"Expected runs.using == 'composite', got {runs.get('using')!r}"
    )


def test_runs_has_steps(action: dict) -> None:
    steps = action["runs"].get("steps")
    assert isinstance(steps, list) and len(steps) > 0, (
        "'runs.steps' must be a non-empty list"
    )


def test_all_declared_inputs_present(action: dict) -> None:
    declared = set(action["inputs"].keys())
    missing = EXPECTED_INPUTS - declared
    assert not missing, f"Expected inputs not found in action.yml: {missing}"


def test_all_inputs_have_description_and_default(action: dict) -> None:
    for name, spec in action["inputs"].items():
        assert isinstance(spec, dict), f"Input '{name}' spec must be a mapping"
        assert "description" in spec, f"Input '{name}' is missing 'description'"
        assert spec["description"].strip(), f"Input '{name}' has empty 'description'"
        assert "default" in spec, f"Input '{name}' is missing 'default'"


def test_all_declared_outputs_present(action: dict) -> None:
    declared = set(action["outputs"].keys())
    missing = EXPECTED_OUTPUTS - declared
    assert not missing, f"Expected outputs not found in action.yml: {missing}"


def test_all_outputs_have_value(action: dict) -> None:
    for name, spec in action["outputs"].items():
        assert isinstance(spec, dict), f"Output '{name}' spec must be a mapping"
        assert "value" in spec, f"Output '{name}' is missing 'value'"
        assert spec["value"], f"Output '{name}' has empty 'value'"


def test_all_outputs_have_description(action: dict) -> None:
    for name, spec in action["outputs"].items():
        assert "description" in spec, f"Output '{name}' is missing 'description'"
        assert spec["description"].strip(), f"Output '{name}' has empty 'description'"


def test_eva_run_step_has_id(action: dict) -> None:
    steps = action["runs"]["steps"]
    ids = [s.get("id") for s in steps]
    assert "eva-run" in ids, (
        "Expected a step with id='eva-run' to produce violations/result outputs"
    )


def test_output_values_reference_eva_run_step(action: dict) -> None:
    for name, spec in action["outputs"].items():
        assert "eva-run" in spec["value"], (
            f"Output '{name}' value should reference steps.eva-run.outputs"
        )


def test_branding_present(action: dict) -> None:
    branding = action.get("branding", {})
    assert "icon" in branding, "action.yml branding is missing 'icon'"
    assert "color" in branding, "action.yml branding is missing 'color'"
