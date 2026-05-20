# US-036 — Meeting Contracts Pack

**ID:** EVA-NEW-MEETING-CONTRACTS
**Status:** paper
**Author:** $USER
**Task:** [T-0148](tlc://hop-top/ops/T-0148) (track: meeting-intake-pipeline)
**Persona:** [Alex — AI Engineer](../personas.md) ·
`individuals/solo-developer.md` (maintained in the shared hop-top personas library, outside this repo)

## User Goal

As Alex, I want a registerable pack of four meeting-domain contracts (length, no-hallucinations,
PII redaction, follow-up actionability) so that LLM-generated meeting summaries and follow-up
lists can be quality-gated by eva — both offline (`eva run --contract`) and inline as `tlc flow`
step gates — without each consumer redefining the rules from scratch.

## Context

- meeting-intake-pipeline track produces summaries + follow-ups from transcripts. Multiple
  consumers (showcase 4a, ops digests, client deliverables) need same quality gate — pack
  centralises it.
- tlc flow integrates eva as Step Gate (see tlc `docs/flows-and-assignees.md`); flow step
  can reference `gate: meeting@0.1`.
- Showcase 4a demos "transcript → summary → digest"; needs visible failure modes
  (hallucination caught, raw email blocked) to land.
- Reuses eva's `contains`/`regex`/`no_pii`/`hallucination`; adds two Tier 3 plugins
  (`cite_coverage`, `followup_shape`).
- Input shape: `{summary: str, followups: [...], metadata: {...}}` —
  `metadata.yaml` carries `participants[]`, `transcript_path`, `pii_ok: bool`.

## Contracts

### 1. `meeting-summary-length-0.1`

Cap summary at 500 words. Hard fail above; warn 400-500.

**Acceptance:**
- pass: 320-word summary
- fail: 700-word summary → exit 1, message `summary length 712 > 500 (max)`
- warn: 450-word summary → mode warn surfaces in report, exit 0

**Sample contract YAML:**

```yaml
name: meeting-summary-length
version: 0.1
provider: meeting-summarizer
evaluators:
  - name: regex
    field: summary
    pattern: '^(\S+\s+){0,500}\S*$'
    mode: binary
  - name: word_count
    field: summary
    max: 500
    warn_above: 400
    mode: threshold
```

**Failure shape:**

```json
{
  "passed": false,
  "contract": "meeting-summary-length",
  "evaluator": "word_count",
  "score": 0.0,
  "reason": "summary length 712 > 500 (max)",
  "field": "summary"
}
```

### 2. `meeting-no-hallucinations-0.1`

Every factual claim cites either a `participants[]` entry from `metadata.yaml` OR a transcript
span (line-ref `L42` or quoted phrase `"..."`). Custom evaluator `cite_coverage` (Tier 3
plugin) splits summary into claim sentences, runs cite-detector + participant-name matcher, plus
fallback to LLM-judge `hallucination` over residual.

**Acceptance:**
- pass: every claim has either a cited line, quoted span, or participant attribution
- fail: claim "the team agreed to a 2-week extension" with no transcript support → exit 1
- combined: summary citing participant `@walid` AND line `L88` for two distinct claims passes

**Sample contract YAML:**

```yaml
name: meeting-no-hallucinations
version: 0.1
provider: meeting-summarizer
evaluators:
  - name: cite_coverage
    field: summary
    sources:
      participants: metadata.participants
      transcript: metadata.transcript_path
    min_coverage: 1.0
    mode: binary
  - name: hallucination
    field: summary
    mode: threshold
    min_score: 0.9
```

**Failure shape:** same envelope as #1 plus
`uncited_claims: ["team agreed to a 2-week extension"]`, `score: 0.66`.

### 3. `meeting-pii-redacted-0.1`

No raw email, phone, SSN, credit card in `summary` field unless `metadata.pii_ok: true`.
Wraps `no_pii` with metadata-conditional bypass.

**Acceptance:**
- pass: summary uses `<participant>` placeholders; raw email absent
- fail: summary includes `walid@spinneys.com` with `pii_ok: false` → exit 1
- pass: same email present but `metadata.pii_ok: true` → exit 0 (opted in)

**Sample contract YAML:**

```yaml
name: meeting-pii-redacted
version: 0.1
provider: meeting-summarizer
evaluators:
  - name: no_pii
    field: summary
    skip_if:
      metadata.pii_ok: true
    mode: binary
```

**Failure shape:**

```json
{
  "passed": false,
  "contract": "meeting-pii-redacted",
  "evaluator": "no_pii",
  "score": 0.0,
  "reason": "raw email detected in summary",
  "matches": [{"type": "email", "value": "walid@..."}]
}
```

### 4. `followup-actionable-0.1`

Each `followups[]` item has: (a) `assignee` (cardamum/aps id or raw name), (b) action verb in
`action` field, (c) concrete `trigger` (deadline date, condition string, or literal "asap").
Custom `followup_shape` evaluator (Tier 3) walks the list.

**Acceptance:**
- pass: `{assignee: "noor", action: "draft", trigger: "2026-05-05"}`
- fail: `{assignee: "noor", action: "do something", trigger: null}` → exit 1
- fail: missing `assignee` → exit 1, message `followup[2] missing assignee`

**Sample contract YAML:**

```yaml
name: followup-actionable
version: 0.1
provider: meeting-summarizer
evaluators:
  - name: followup_shape
    field: followups
    require:
      - assignee
      - action
      - trigger
    action_verbs_min: 1
    triggers_allowed: [date, condition, "asap"]
    mode: binary
```

**Failure shape:** same envelope plus per-item detail —
`items: [{index: 1, missing: ["trigger"]}, {index: 2, issue: "no_verb"}]`.

## Pack Manifest

Single registration step installs all 4 contracts + the 2 custom evaluators
(`cite_coverage`, `followup_shape`). Pack file: `evals/packs/meeting-0.1.yaml`.

```yaml
pack: meeting
version: 0.1
contracts:
  - meeting-summary-length-0.1
  - meeting-no-hallucinations-0.1
  - meeting-pii-redacted-0.1
  - followup-actionable-0.1
plugins:
  - cite_coverage
  - followup_shape
```

Install: `eva pack install evals/packs/meeting-0.1.yaml`. Combined gate: `eva run --pack meeting`
runs all 4 against same input artefact; aggregate exit code = OR of individual fails.

## Acceptance Criteria (Story-Level)

1. Each of the 4 contracts is registerable + invocable via `eva run --contract <path>`.
2. Each contract passes on conformant fixture in `tests/e2e/contracts/meeting/fixtures/good/`.
3. Each contract fails with descriptive message on injected violation in `fixtures/bad/`.
4. Combined gate via `eva run --pack meeting --input <artefact>` runs all 4; aggregate
   pass/fail with per-contract breakdown in JSON output.
5. Contracts compose with existing eva contract registry (no name collision; `eva contract
   validate` passes for each).
6. Each contract carries semver in `name@version` form (e.g. `meeting-summary-length@0.1`)
   and `eva contract diff` recognises version bumps.
7. Pack ships as single artefact (`evals/packs/meeting-0.1.yaml`) — one install command
   registers all 4 contracts + 2 plugins.
8. tlc flow step can reference pack via `gate: meeting@0.1`; smoke flow in
   meeting-intake-pipeline track exercises end-to-end gate.
9. Custom evaluators (`cite_coverage`, `followup_shape`) ship as Tier 3 plugins; documented
   in `docs/plugin-authoring-guide.md`.
10. Failure response shape is uniform JSON across all 4 (fields: `passed`, `contract`,
    `evaluator`, `score`, `reason`, plus contract-specific detail).

## E2E Tests (planned)

Path: `tests/e2e/contracts/meeting/`. Pattern follows existing
`tests/e2e/test_run_contract_cli.py` + `test_content_evaluators.py`.

1. `test_meeting_summary_length_pass.py` — 320-word summary → exit 0
2. `test_meeting_summary_length_fail.py` — 712-word summary → exit 1, reason matches regex
3. `test_meeting_no_hallucinations_pass.py` — every claim cites participant or line ref
4. `test_meeting_no_hallucinations_fail.py` — injected uncited claim → exit 1
5. `test_meeting_pii_redacted_pass.py` — placeholder summary + pii_ok false → exit 0;
   raw-email summary + pii_ok true → exit 0 (opt-in path)
6. `test_meeting_pii_redacted_fail.py` — raw email + pii_ok false → exit 1
7. `test_followup_actionable_pass.py` — full assignee/action/trigger triple
8. `test_followup_actionable_fail.py` — missing trigger / vague action → exit 1
9. `test_meeting_pack_combined.py` — pack-mode `eva run --pack meeting` aggregates 4 contracts;
   one bad artefact fails 2 contracts; JSON output enumerates both failures
10. `test_meeting_pack_tlc_flow_smoke.py` — tlc flow exec step + eva gate=meeting@0.1;
    confirms gateway-mode integration (skips if `tlc` binary absent on PATH)

## Related

- Track: meeting-intake-pipeline (`~/.ops/.tlc/tracks/meeting-intake-pipeline/`)
- Showcase scenario 4a: tools-showcase-scenarios track
- tlc flow gates: `~/.w/ideacrafterslabs/tlc/hops/main/docs/flows-and-assignees.md`
- Existing evaluators reused: `contains`, `regex`, `no_pii`, `hallucination`
- New plugins: `cite_coverage`, `followup_shape` (docs/plugin-authoring-guide.md)
- Blocks: T-0156 (Add eva contract gates to flow)
