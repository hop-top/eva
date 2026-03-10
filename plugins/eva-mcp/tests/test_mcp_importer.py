import json
import pytest
from pathlib import Path
from eva_mcp.importer import import_mcp_manifest, contracts_to_yaml, MCPImportError

FIXTURES = Path(__file__).parent / "fixtures"


def test_import_produces_contracts_per_tool():
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    assert len(contracts) == 2


def test_import_contract_names():
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    names = [c.name for c in contracts]
    assert "file-tools.read_file" in names
    assert "file-tools.write_file" in names


def test_import_preserves_input_schema():
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    read = next(c for c in contracts if "read_file" in c.name)
    assert "path" in read.request_schema.get("required", [])
    assert "path" in read.request_schema.get("properties", {})


def test_import_sets_provider():
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    for c in contracts:
        assert c.provider == "file-tools"


def test_import_missing_name_raises():
    with pytest.raises(MCPImportError, match="name"):
        import_mcp_manifest({"tools": []})


def test_import_empty_tools_list():
    manifest = {"name": "empty-server", "tools": []}
    contracts = import_mcp_manifest(manifest)
    assert contracts == []


def test_import_tool_without_input_schema():
    manifest = {
        "name": "bare-tools",
        "tools": [{"name": "ping", "description": "Ping the server"}],
    }
    contracts = import_mcp_manifest(manifest)
    assert len(contracts) == 1
    assert contracts[0].request_schema == {}


def test_to_yaml_roundtrip(tmp_path):
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    paths = contracts_to_yaml(contracts, tmp_path / "out")
    assert len(paths) == 2
    for p in paths:
        import yaml
        data = yaml.safe_load(p.read_text())
        assert "name" in data
        assert "provider" in data
        assert data["provider"] == "file-tools"
