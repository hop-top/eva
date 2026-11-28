"""Shape, budget, links and command drift of the bundled agent skill."""
import re
import shlex
from pathlib import Path

import pytest
import typer.main
import yaml

import cli
from cli.main import app

SKILL_DIR = Path(cli.__file__).resolve().parent / "skills" / "eva-cli"
SKILL_MD = SKILL_DIR / "SKILL.md"
MAX_LINES = 80
MAX_WORDS = 600

FENCE = re.compile(r"^(```|~~~)")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
PATH_MENTION = re.compile(r"(?<![\w/.-])(references|scripts)/[\w./-]+\.\w+")


def _split(text: str) -> tuple[dict, str]:
    assert text.startswith("---\n"), "missing frontmatter"
    head, sep, body = text[4:].partition("\n---\n")
    assert sep, "unterminated frontmatter"
    meta = yaml.safe_load(head)
    assert isinstance(meta, dict)
    return meta, body


def _md_files() -> list[Path]:
    return sorted(SKILL_DIR.rglob("*.md"))


# --- shape -----------------------------------------------------------------


def test_skill_md_exists():
    assert SKILL_MD.is_file()


def test_frontmatter_parses_with_only_name_and_description():
    meta, _ = _split(SKILL_MD.read_text())
    assert set(meta) == {"name", "description"}


def test_name_is_eva_cli_and_matches_folder():
    meta, _ = _split(SKILL_MD.read_text())
    assert meta["name"] == "eva-cli"
    assert SKILL_DIR.name == meta["name"]
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta["name"])
    assert len(meta["name"]) <= 64


def test_description_limits_and_trigger():
    meta, _ = _split(SKILL_MD.read_text())
    desc = meta["description"]
    assert isinstance(desc, str) and desc.strip()
    assert len(desc) <= 1024
    assert "Use when" in desc
    assert "\n" not in desc.strip()


def test_body_within_budget():
    _, body = _split(SKILL_MD.read_text())
    lines = body.strip("\n").splitlines()
    words = body.split()
    assert len(lines) <= MAX_LINES, f"{len(lines)} lines"
    assert len(words) <= MAX_WORDS, f"{len(words)} words"


def test_no_scripts_folder():
    assert not (SKILL_DIR / "scripts").exists()


# --- links -----------------------------------------------------------------


def broken_links(md: Path, root: Path) -> list[str]:
    """Relative links and path mentions in md that do not resolve inside root."""
    text = md.read_text()
    bad: list[str] = []
    targets = LINK.findall(text) + [m.group(0) for m in PATH_MENTION.finditer(text)]
    for raw in targets:
        if re.match(r"[a-z][a-z0-9+.-]*:", raw) or raw.startswith("#"):
            continue
        rel = raw.split("#", 1)[0]
        base = root if PATH_MENTION.fullmatch(raw) else md.parent
        resolved = (base / rel).resolve()
        if root.resolve() not in resolved.parents and resolved != root.resolve():
            bad.append(f"{raw} leaves the skill folder")
        elif not resolved.exists():
            bad.append(f"{raw} does not exist")
    return list(dict.fromkeys(bad))


@pytest.mark.parametrize("md", _md_files(), ids=lambda p: str(p.relative_to(SKILL_DIR)))
def test_links_resolve_inside_skill_folder(md):
    assert broken_links(md, SKILL_DIR) == []


def test_link_checker_flags_escapes_and_missing(tmp_path):
    root = tmp_path / "skill"
    (root / "references").mkdir(parents=True)
    (tmp_path / "outside.md").write_text("x")
    (root / "references" / "ok.md").write_text("ok")
    md = root / "SKILL.md"
    md.write_text(
        "[a](references/ok.md) [b](../outside.md) [c](references/gone.md) "
        "[d](https://example.com) see `references/ok.md` and references/nope.md"
    )
    bad = broken_links(md, root)
    assert len(bad) == 3
    assert any("outside.md" in b for b in bad)
    assert any("gone.md" in b for b in bad)
    assert any("nope.md" in b for b in bad)


def test_every_reference_is_linked_from_body():
    body = SKILL_MD.read_text()
    refs = sorted((SKILL_DIR / "references").glob("*.md"))
    assert refs, "expected at least one reference file"
    for ref in refs:
        assert f"references/{ref.name}" in body, f"{ref.name} not mentioned in SKILL.md"


# --- drift: commands and flags against the real CLI tree -------------------

ROOT = typer.main.get_command(app)
STOP = {"|", "||", "&&", ";", ">", ">>", "<", "2>&1", "&"}


# Duck-typed on purpose: newer typer vendors its own click, so the command
# classes are not click.Command / click.Group.
def _long_opts(cmd) -> set[str]:
    opts = {"--help"}
    for p in cmd.params:
        opts.update(o for o in [*p.opts, *p.secondary_opts] if o.startswith("--"))
    return opts


def check_command(line: str) -> list[str]:
    """Problems with one `eva ...` line, judged against the live click tree."""
    try:
        tokens = shlex.split(line, comments=False)
    except ValueError:
        tokens = line.split()
    assert tokens and tokens[0] == "eva"
    cur = ROOT
    allowed = _long_opts(ROOT) | {"--install-completion", "--show-completion"}
    path = ["eva"]
    errors: list[str] = []
    descending = True
    for tok in tokens[1:]:
        if tok in STOP:
            break
        if tok.startswith("--"):
            flag = tok.split("=", 1)[0]
            if flag == "--":
                break
            if flag not in allowed:
                errors.append(f"{' '.join(path)}: unknown flag {flag}")
            continue
        if tok.startswith("-") or tok.startswith("<"):
            descending = descending and not tok.startswith("<")
            continue
        if descending and getattr(cur, "commands", None):
            if tok in cur.commands:
                cur = cur.commands[tok]
                path.append(tok)
                allowed = allowed | _long_opts(cur)
            else:
                errors.append(f"{' '.join(path)}: unknown command {tok!r}")
                descending = False
        else:
            descending = False
    return errors


def extract_eva_lines(text: str) -> list[str]:
    """`eva ...` lines from fenced blocks (continuations joined) and inline code."""
    found: list[str] = []
    in_fence = False
    pending = ""
    for raw in text.splitlines():
        if FENCE.match(raw.strip()):
            in_fence = not in_fence
            pending = ""
            continue
        if in_fence:
            line = raw.strip()
            if pending:
                line = pending + " " + line
                pending = ""
            if line.endswith("\\"):
                pending = line[:-1].strip()
                continue
            line = re.sub(r"^\$\s+", "", line)
            if line.startswith("eva "):
                found.append(line)
        else:
            for span in INLINE_CODE.findall(raw):
                span = span.strip()
                if span.startswith("eva "):
                    found.append(span)
    return found


def _skill_lines() -> list[tuple[str, str]]:
    out = []
    for md in _md_files():
        for line in extract_eva_lines(md.read_text()):
            out.append((str(md.relative_to(SKILL_DIR)), line))
    return out


def test_skill_names_some_commands():
    assert len(_skill_lines()) >= 8


@pytest.mark.parametrize("where,line", _skill_lines())
def test_eva_commands_exist_in_cli_tree(where, line):
    assert check_command(line) == [], f"{where}: {line}"


def test_drift_checker_accepts_real_and_rejects_fake():
    assert check_command("eva run --contract c.yaml --input - --format json") == []
    assert check_command("eva contract diff a.yaml b.yaml") == []
    assert check_command("eva skill install --dir /tmp/x --dry-run --force") == []
    assert check_command("eva runs list --status fail | head") == []
    assert check_command("eva --help") == []
    assert check_command("eva <group> --help") == []
    assert check_command("eva contracts validate c.yaml")
    assert check_command("eva contract validate --strict c.yaml")
    assert check_command("eva run --nonexistent")
    assert check_command("eva runs list --left x")


def test_extractor_handles_fences_continuations_and_inline():
    text = (
        "Use `eva runs list --limit 3` now.\n"
        "```bash\n$ eva run \\\n  --dataset d.yaml \\\n  --no-tui\nls\n```\n"
        "`not eva` and `eva.yaml`\n"
    )
    assert extract_eva_lines(text) == [
        "eva runs list --limit 3",
        "eva run --dataset d.yaml --no-tui",
    ]


# --- examples in the references must be valid ------------------------------


def test_contract_example_in_reference_validates(tmp_path):
    from core.contract import load_contract

    text = (SKILL_DIR / "references" / "contract-yaml.md").read_text()
    blocks = re.findall(r"```yaml\n(.*?)```", text, re.S)
    assert blocks
    for i, block in enumerate(blocks):
        f = tmp_path / f"c{i}.yaml"
        f.write_text(block)
        assert load_contract(f).name
