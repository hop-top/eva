# Eva Cheatsheet — Agent

The agent reference ships inside the package as a skill, so it always matches
the installed version. Read it from the CLI:

```bash
eva skill show                  # when and how to use eva: modes, exit codes, escalation, gotchas
eva skill show rest-api         # gateway routes, auth header, status codes
eva skill show contract-yaml    # contract fields, modes, evaluators
eva skill install               # copy the skill to ~/.claude/skills/eva-cli
```

Source: [`cli/skills/eva-cli/`](../cli/skills/eva-cli/). Edit it there; this page
holds no copy. Request and response schemas: [gateway-api.md](gateway-api.md).
Flags: [cli-reference.md](cli-reference.md).
