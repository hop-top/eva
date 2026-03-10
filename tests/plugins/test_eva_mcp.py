"""Unit tests for eva-mcp importer."""
import json
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent.parent.parent / "plugins/eva-mcp/tests/fixtures"


def test_import_produces_contracts_per_tool():
    from eva_mcp.importer import import_mcp_manifest
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    assert len(contracts) == 2


def test_import_contract_names():
    from eva_mcp.importer import import_mcp_manifest
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    names = [c.name for c in contracts]
    assert "file-tools.read_file" in names
    assert "file-tools.write_file" in names


def test_import_sets_provider():
    from eva_mcp.importer import import_mcp_manifest
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    for c in contracts:
        assert c.provider == "file-tools"


def test_import_missing_name_raises():
    from eva_mcp.importer import import_mcp_manifest, MCPImportError
    with pytest.raises(MCPImportError, match="name"):
        import_mcp_manifest({"tools": []})


def test_import_empty_tools_returns_empty_list():
    from eva_mcp.importer import import_mcp_manifest
    contracts = import_mcp_manifest({"name": "empty-server", "tools": []})
    assert contracts == []


def test_import_tool_without_schema_uses_empty():
    from eva_mcp.importer import import_mcp_manifest
    manifest = {"name": "bare", "tools": [{"name": "ping"}]}
    contracts = import_mcp_manifest(manifest)
    assert contracts[0].request_schema == {}


def test_contracts_to_yaml(tmp_path):
    from eva_mcp.importer import import_mcp_manifest, contracts_to_yaml
    import yaml
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    paths = contracts_to_yaml(contracts, tmp_path / "out")
    assert len(paths) == 2
    for p in paths:
        data = yaml.safe_load(p.read_text())
        assert data["provider"] == "file-tools"
