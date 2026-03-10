# Eva Invite System — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan
> task-by-task.

<!-- Task list
  T-xxxx Task 1  [eva-pkg] Worker — invite creation endpoint (POST /admin/invites)
  T-xxxx Task 2  [eva-pkg] Worker — redeem endpoint (POST /redeem)
  T-xxxx Task 3  [eva]     invite command group scaffold
  T-xxxx Task 4  [eva]     eva invite codes — list local invite codes
  T-xxxx Task 5  [eva]     eva invite share <email> — share a code
  T-xxxx Task 6  [eva]     eva signup <code> <email> — redeem code
  T-xxxx Task 7  [eva-pkg] Admin — seed invites justfile target
-->

**Goal:** Partner-controlled invite system. Partners distribute short codes; recipients redeem for
personal access tokens. All invite state tracked in Worker KV + local `~/.eva/invites.json`.

**Architecture:**
- `eva-pkg` Cloudflare Worker — source of truth; KV stores invite records
- `eva` CLI — local state cache (`~/.eva/invites.json`); calls Worker endpoints
- Flow: admin seeds codes → partner shares via `eva invite share` → recipient runs `eva signup`

**Tech Stack:**
- Worker: Cloudflare Workers + KV (eva-pkg repo, separate from this repo)
- CLI: Python, typer, rich, httpx, PyYAML
- Local state: `~/.eva/invites.json` (JSON), `~/.eva/config.yml` (YAML)

**Assumes:** Phase 5 complete; eva-pkg Worker deployed; partner token auth in place.

---

## Prerequisites (eva-pkg tasks — implement in eva-pkg repo first)

> Tasks 1–2 are in the `eva-pkg` Cloudflare Worker repo, not this repo.
> Complete and deploy before implementing Tasks 3–7.

---

### Task 1: [eva-pkg] Worker — invite creation endpoint

**Repo:** `eva-pkg` (Cloudflare Worker)

**Endpoint:** `POST /admin/invites`

**Auth:** `Authorization: Bearer <admin_secret>` header; reject 401 if missing/wrong.

**Request body:**
```pseudocode
{ partner_token: string, count: integer }
```

**Logic:**
```pseudocode
validate admin_secret from Authorization header
generate count codes:
  each code = "EVA-" + random_alphanumeric(4)  // e.g. EVA-X7K2
  KV key: "invite:<CODE>"
  KV value (JSON):
    { code, created_by: partner_token, created_at: ISO8601,
      redeemed: false, redeemed_by: null, redeemed_at: null,
      downloads: 0 }
return { codes: ["EVA-X7K2", ...] }
```

**Response:** `200 { codes: string[] }`

**Errors:**
- `400` — missing/invalid body fields
- `401` — bad admin secret
- `500` — KV write failure

**KV namespace:** `EVA_INVITES`

**Expected outcome:** `curl -X POST .../admin/invites -d '{"partner_token":"tk_x","count":5}'`
returns JSON array of 5 codes; each stored in KV.

**Commit message:** `feat(worker): POST /admin/invites — generate invite codes in KV`

---

### Task 2: [eva-pkg] Worker — redeem endpoint

**Repo:** `eva-pkg` (Cloudflare Worker)

**Endpoint:** `POST /redeem` — public, no auth required.

**Request body:**
```pseudocode
{ code: string, email: string }
```

**Logic:**
```pseudocode
lookup KV key "invite:<code>"
if not found: return 404 { error: "invalid_code" }
if record.redeemed: return 409 { error: "already_redeemed" }

personal_token = create_partner_token(email, limit=100)
  // reuse existing partner creation logic in Worker

mark KV record:
  redeemed = true
  redeemed_by = email
  redeemed_at = ISO8601 now

install_pip = "pip install eva --index-url https://<personal_token>@eva-pkg..."
install_uv  = "uv add eva --index-url https://<personal_token>@eva-pkg..."

return 200 { token: personal_token, install_pip, install_uv }
```

**Errors:**
- `400` — missing body fields
- `404` — code not found
- `409` — code already redeemed

**Expected outcome:** `curl -X POST .../redeem -d '{"code":"EVA-X7K2","email":"x@y.com"}'`
returns token + install strings; second call with same code returns `409`.

**Commit message:** `feat(worker): POST /redeem — validate code, issue personal token`

---

## Eva CLI tasks (this repo)

---

### Task 3: invite command group scaffold

**Files:**
- Create: `cli/commands/invite.py`
- Edit: `cli/main.py` — register `invite_app` typer group
- Create: `tests/e2e/test_invite_cmd.py`

**Steps:**

1. Create `cli/commands/` dir (if not exists); add `__init__.py`.

2. Create `cli/commands/invite.py`:
```pseudocode
invite_app = typer.Typer(help="Manage invite codes.")

// no commands yet — added in Tasks 4 + 5
```

3. Edit `cli/main.py` — add after `drift_app` block:
```pseudocode
from cli.commands.invite import invite_app
app.add_typer(invite_app, name="invite")
```

4. Create `tests/e2e/test_invite_cmd.py` with placeholder:
```pseudocode
def test_invite_help_shows():
    result = runner.invoke(app, ["invite", "--help"])
    assert result.exit_code == 0
    assert "invite" in result.output
```

5. Run: `PATH=/opt/homebrew/bin:$HOME/.local/bin:$PATH just test`
   Expected: placeholder test passes.

**Expected outcome:** `eva invite --help` shows invite group; test green.

**Commit message:** `feat(cli): eva invite command group scaffold`

---

### Task 4: `eva invite codes` — list local invite codes

**Files:**
- Edit: `cli/commands/invite.py`
- Edit: `tests/e2e/test_invite_cmd.py`

**State file:** `~/.eva/invites.json`
```pseudocode
{
  "codes": [
    { "code": "EVA-X7K2", "status": "available" },
    { "code": "EVA-M3N4", "status": "sent", "sent_to": "alice@x.com" }
  ]
}
```

**Steps:**

1. Write failing test first:
```pseudocode
def test_invite_codes_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_HOME", str(tmp_path))
    result = runner.invoke(app, ["invite", "codes"])
    assert "No invite codes" in result.output

def test_invite_codes_table(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_HOME", str(tmp_path))
    write_invites_json(tmp_path, codes=[
        {"code": "EVA-X7K2", "status": "available"},
        {"code": "EVA-M3N4", "status": "sent", "sent_to": "alice@x.com"},
    ])
    result = runner.invoke(app, ["invite", "codes"])
    assert "EVA-X7K2" in result.output
    assert "available" in result.output
    assert "EVA-M3N4" in result.output
    assert "sent" in result.output
```

2. Implement `codes` subcommand in `cli/commands/invite.py`:
```pseudocode
EVA_HOME = Path(os.environ.get("EVA_HOME", "~/.eva")).expanduser()
INVITES_FILE = EVA_HOME / "invites.json"

@invite_app.command("codes")
def invite_codes():
    """List local invite codes."""
    if not INVITES_FILE.exists():
        console.print("[yellow]No invite codes. Contact eva@hop.top.[/yellow]")
        return

    data = json.loads(INVITES_FILE.read_text())
    table = Table(title="Invite Codes")
    table.add_column("Code", style="cyan")
    table.add_column("Status")
    table.add_column("Sent To")

    for entry in data["codes"]:
        status_style = {
            "available": "[green]available[/green]",
            "sent":      "[yellow]sent[/yellow]",
            "redeemed":  "[dim]redeemed[/dim]",
        }.get(entry["status"], entry["status"])
        table.add_row(entry["code"], status_style, entry.get("sent_to", ""))

    console.print(table)
```

3. Run: `PATH=/opt/homebrew/bin:$HOME/.local/bin:$PATH just test tests/e2e/test_invite_cmd.py`
   Expected: both tests green.

**Expected outcome:**
```
eva invite codes
┌──────────┬───────────┬──────────────┐
│ Code     │ Status    │ Sent To      │
├──────────┼───────────┼──────────────┤
│ EVA-X7K2 │ available │              │
│ EVA-M3N4 │ sent      │ alice@x.com  │
└──────────┴───────────┴──────────────┘
```

**Commit message:** `feat(cli): eva invite codes — list local invite codes`

---

### Task 5: `eva invite share <email>` — share a code

**Files:**
- Edit: `cli/commands/invite.py`
- Edit: `tests/e2e/test_invite_cmd.py`

**Steps:**

1. Write failing tests:
```pseudocode
def test_invite_share_no_available(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_HOME", str(tmp_path))
    write_invites_json(tmp_path, codes=[
        {"code": "EVA-X7K2", "status": "sent", "sent_to": "bob@x.com"}
    ])
    result = runner.invoke(app, ["invite", "share", "alice@x.com"])
    assert result.exit_code == 1
    assert "No available" in result.output

def test_invite_share_prints_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_HOME", str(tmp_path))
    write_invites_json(tmp_path, codes=[
        {"code": "EVA-X7K2", "status": "available"}
    ])
    result = runner.invoke(app, ["invite", "share", "alice@x.com"])
    assert "EVA-X7K2" in result.output
    assert "eva signup" in result.output
    assert "alice@x.com" not in result.output or "alice@x.com" in result.output

def test_invite_share_marks_sent(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_HOME", str(tmp_path))
    write_invites_json(tmp_path, codes=[
        {"code": "EVA-X7K2", "status": "available"}
    ])
    runner.invoke(app, ["invite", "share", "alice@x.com"])
    data = json.loads((tmp_path / "invites.json").read_text())
    assert data["codes"][0]["status"] == "sent"
    assert data["codes"][0]["sent_to"] == "alice@x.com"
```

2. Implement `share` subcommand:
```pseudocode
@invite_app.command("share")
def invite_share(email: str = typer.Argument(..., help="Recipient email")):
    """Send one unused invite code to an email address (prints draft)."""
    data = load_invites()  // raises if file missing
    available = [c for c in data["codes"] if c["status"] == "available"]

    if not available:
        console.print("[red]No available invite codes.[/red]")
        raise typer.Exit(1)

    entry = available[0]
    entry["status"] = "sent"
    entry["sent_to"] = email
    save_invites(data)

    code = entry["code"]
    console.print(Panel(
        f"To: {email}\n"
        f"Subject: Your Eva invite\n\n"
        f"Hi,\n\n"
        f"Here is your Eva invite code: [bold cyan]{code}[/bold cyan]\n\n"
        f"Run to get started:\n\n"
        f"  eva signup {code} {email}\n\n"
        f"Then install:\n\n"
        f"  pip install eva\n",
        title="[bold]Email Draft[/bold]",
        expand=False,
    ))
    console.print(f"[green]Code {code} marked as sent.[/green]")
```

3. Run: `PATH=/opt/homebrew/bin:$HOME/.local/bin:$PATH just test tests/e2e/test_invite_cmd.py`
   Expected: all tests green.

**Expected outcome:**
```
eva invite share alice@example.com
╭──────────── Email Draft ────────────╮
│ To: alice@example.com               │
│ Subject: Your Eva invite            │
│                                     │
│ Hi,                                 │
│                                     │
│ Your Eva invite code: EVA-X7K2      │
│                                     │
│ Run to get started:                 │
│   eva signup EVA-X7K2 alice@...     │
│                                     │
│ Then install:                       │
│   pip install eva                   │
╰─────────────────────────────────────╯
Code EVA-X7K2 marked as sent.
```

**Commit message:** `feat(cli): eva invite share — pick code, mark sent, print email draft`

---

### Task 6: `eva signup <code> <email>` — redeem code

**Files:**
- Edit: `cli/main.py` — add top-level `signup` command
- Create: `tests/e2e/test_signup_cmd.py`

**Steps:**

1. Write failing tests (httpx mock):
```pseudocode
def test_signup_success(tmp_path, monkeypatch, respx_mock):
    monkeypatch.setenv("EVA_HOME", str(tmp_path))
    respx_mock.post("https://eva-pkg...workers.dev/redeem").mock(return_value=Response(200,
        json={"token": "tk_abc123", "install_pip": "pip install eva --index-url ...",
              "install_uv": "uv add eva --index-url ..."}))
    result = runner.invoke(app, ["signup", "EVA-X7K2", "me@x.com"])
    assert result.exit_code == 0
    assert "tk_abc123" in result.output or "pip install eva" in result.output
    config = (tmp_path / "config.yml").read_text()
    assert "tk_abc123" in config

def test_signup_already_redeemed(tmp_path, monkeypatch, respx_mock):
    monkeypatch.setenv("EVA_HOME", str(tmp_path))
    respx_mock.post("...").mock(return_value=Response(409,
        json={"error": "already_redeemed"}))
    result = runner.invoke(app, ["signup", "EVA-X7K2", "me@x.com"])
    assert result.exit_code == 1
    assert "already redeemed" in result.output.lower()

def test_signup_invalid_code(tmp_path, monkeypatch, respx_mock):
    monkeypatch.setenv("EVA_HOME", str(tmp_path))
    respx_mock.post("...").mock(return_value=Response(404,
        json={"error": "invalid_code"}))
    result = runner.invoke(app, ["signup", "EVA-ZZZZ", "me@x.com"])
    assert result.exit_code == 1
    assert "invalid" in result.output.lower()
```

2. Implement `signup` command in `cli/main.py`:
```pseudocode
WORKER_BASE = "https://eva-pkg.ideacrafters-llc.workers.dev"

@app.command()
def signup(
    code:  str = typer.Argument(..., help="Invite code (e.g. EVA-X7K2)"),
    email: str = typer.Argument(..., help="Your email address"),
):
    """Redeem an invite code and save personal access token."""
    import httpx, yaml

    eva_home = Path(os.environ.get("EVA_HOME", "~/.eva")).expanduser()
    eva_home.mkdir(parents=True, exist_ok=True)

    resp = httpx.post(f"{WORKER_BASE}/redeem", json={"code": code, "email": email})

    if resp.status_code == 409:
        console.print("[red]Error:[/red] code already redeemed.")
        raise typer.Exit(1)
    if resp.status_code == 404:
        console.print("[red]Error:[/red] invalid code.")
        raise typer.Exit(1)
    if resp.status_code != 200:
        console.print(f"[red]Error:[/red] unexpected response {resp.status_code}.")
        raise typer.Exit(1)

    body = resp.json()
    token = body["token"]
    index_url = f"https://{token}@eva-pkg.ideacrafters-llc.workers.dev/simple/"

    config_file = eva_home / "config.yml"
    config = {"index_url": index_url, "token": token}
    config_file.write_text(yaml.dump(config))

    console.print(f"[green]Success![/green] Token saved to {config_file}")
    console.print(f"\nInstall Eva:\n  {body['install_pip']}")
    console.print(f"\nOr with uv:\n  {body['install_uv']}")
    console.print("\nRun [bold]pip install eva[/bold] to get started.")
```

3. Run: `PATH=/opt/homebrew/bin:$HOME/.local/bin:$PATH just test tests/e2e/test_signup_cmd.py`
   Expected: all three tests green.

4. Verify config written correctly:
```pseudocode
eva signup EVA-X7K2 me@example.com
// check ~/.eva/config.yml contains token + index_url
```

**Expected outcome:**
```
eva signup EVA-X7K2 me@example.com
Success! Token saved to /Users/<you>/.eva/config.yml

Install Eva:
  pip install eva --index-url https://tk_abc123@eva-pkg...

Or with uv:
  uv add eva --index-url https://tk_abc123@eva-pkg...

Run pip install eva to get started.
```

**Config written:**
```pseudocode
// ~/.eva/config.yml
index_url: https://tk_abc123@eva-pkg.ideacrafters-llc.workers.dev/simple/
token: tk_abc123
```

**Commit message:** `feat(cli): eva signup — redeem invite code, save token to ~/.eva/config.yml`

---

### Task 7: [eva-pkg] Admin — seed invites justfile target

**Repo:** `eva-pkg`

**File:** `justfile` (edit)

**Steps:**

1. Add recipe to `eva-pkg` justfile:
```pseudocode
# Seed N invite codes for a partner token.
# Usage: just seed-invites <partner_token> <count>
seed-invites partner_token count:
    curl -s -X POST \
      -H "Authorization: Bearer $ADMIN_SECRET" \
      -H "Content-Type: application/json" \
      -d '{"partner_token":"{{partner_token}}","count":{{count}}}' \
      https://eva-pkg.ideacrafters-llc.workers.dev/admin/invites \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Generated codes:')
for code in data['codes']:
    print(f'  {code}')
print()
print('Share with partner — one code per recipient.')
"
```

2. Verify `ADMIN_SECRET` env var documented in `eva-pkg` README.

3. Test locally against deployed Worker:
```pseudocode
just seed-invites tk_partner_abc 5
// expect: 5 EVA-XXXX codes printed
```

**Expected outcome:**
```
Generated codes:
  EVA-X7K2
  EVA-M3N4
  EVA-P9Q1
  EVA-R5S8
  EVA-T2U6

Share with partner — one code per recipient.
```

**Commit message:** `feat(infra): just seed-invites — generate + print invite codes for partner`

---

## Full flow (integration smoke-test)

```pseudocode
// 1. Admin seeds codes (eva-pkg)
ADMIN_SECRET=xxx just seed-invites tk_partner_abc 3
// → EVA-X7K2, EVA-M3N4, EVA-P9Q1 printed

// 2. Partner lists codes — copy codes into ~/.eva/invites.json
eva invite codes

// 3. Partner shares to recipient
eva invite share alice@example.com
// → prints email draft; marks EVA-X7K2 as sent

// 4. Recipient redeems
eva signup EVA-X7K2 alice@example.com
// → saves ~/.eva/config.yml; prints pip install command

// 5. Recipient installs
pip install eva
```

---

## Local state schema

**`~/.eva/invites.json`**
```pseudocode
{
  "codes": [
    { "code": "EVA-X7K2", "status": "available" },
    { "code": "EVA-M3N4", "status": "sent", "sent_to": "alice@x.com" },
    { "code": "EVA-P9Q1", "status": "redeemed" }
  ]
}
```

Status values: `available` | `sent` | `redeemed`

**`~/.eva/config.yml`** (written by `eva signup`)
```pseudocode
index_url: https://<token>@eva-pkg.ideacrafters-llc.workers.dev/simple/
token: tk_abc123...
```

---

## KV record schema (eva-pkg)

Key: `invite:<CODE>`
```pseudocode
{
  code:         string,       // "EVA-X7K2"
  created_by:   string,       // partner_token
  created_at:   ISO8601,
  redeemed:     boolean,
  redeemed_by:  string|null,  // email
  redeemed_at:  ISO8601|null,
  downloads:    integer        // future: track pip install hits
}
```

---

## Worker endpoint reference

| Method | Path              | Auth         | Description                        |
|--------|-------------------|--------------|------------------------------------|
| POST   | `/admin/invites`  | admin secret | Generate N codes for partner token |
| GET    | `/admin/invites`  | admin secret | List all codes + redemption status |
| POST   | `/redeem`         | none (public)| Redeem code, return personal token |

> `GET /admin/invites` — list endpoint; implement in eva-pkg alongside Task 1.
> Returns array of KV records; useful for audit/support.
