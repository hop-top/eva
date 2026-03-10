# A2A + MCP Integration Guide

Eva can import external agent definitions and turn them into contract YAML files
ready for `eva serve`.

---

## A2A Agent Cards

**Agent-to-Agent (A2A)** is a Google-proposed interoperability protocol for AI
agents. An *Agent Card* is a JSON document that describes an agent's identity,
skills, and input schemas.

Eva reads the `skills` array and emits one contract per skill.

### Agent Card → Contract YAML

**Input (Agent Card JSON):**

```json
{
  "name": "weather-agent",
  "description": "Provides weather forecasts",
  "skills": [
    {
      "name": "get-forecast",
      "description": "Returns a weather forecast for a location",
      "inputSchema": {
        "type": "object",
        "properties": {
          "location": {"type": "string"}
        },
        "required": ["location"]
      }
    }
  ]
}
```

**Output (`weather-agent_get-forecast.yaml`):**

```yaml
name: weather-agent.get-forecast
provider: weather-agent
request_schema:
  type: object
  properties:
    location:
      type: string
  required:
    - location
evaluators: []
retry_policy:
  max_retries: 2
  hint: null
  backoff_ms: 0
```

> Generated contracts have empty `evaluators`. Add evaluators and tighten
> `retry_policy` before deploying.

---

## MCP Manifests

**Model Context Protocol (MCP)** is Anthropic's standard for tool-equipped AI
servers. An MCP *manifest* describes the server's tools and their input schemas.

Eva reads the `tools` array and emits one contract per tool.

### MCP Manifest → Contract YAML

**Input (MCP manifest JSON):**

```json
{
  "name": "search-server",
  "tools": [
    {
      "name": "web_search",
      "description": "Search the web",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": {"type": "string"}
        },
        "required": ["query"]
      }
    }
  ]
}
```

**Output (`search-server_web_search.yaml`):**

```yaml
name: search-server.web_search
provider: search-server
request_schema:
  type: object
  properties:
    query:
      type: string
  required:
    - query
evaluators: []
retry_policy:
  max_retries: 2
  hint: null
  backoff_ms: 0
```

---

## End-to-End Workflow

### A2A workflow

```
1. Obtain Agent Card JSON
   - From agent's /.well-known/agent.json
   - Or hand-authored

2. Import → contract YAML
   eva-a2a convert agent-card.json --output-dir ./contracts

3. Review generated contracts
   - Add evaluators (contains, regex, json_schema_valid, no_pii, ...)
   - Set retry_policy as needed

4. Validate
   eva contract validate ./contracts/<name>.yaml

5. Serve
   eva serve --contracts-dir ./contracts

6. Invoke
   POST /v1/contract/invoke  {"contract": "<name>", "body": {...}}
```

### MCP workflow

```
1. Obtain MCP manifest JSON
   - From MCP server's /manifest endpoint
   - Or hand-authored

2. Import → contract YAML
   eva-mcp convert mcp-manifest.json --output-dir ./contracts

3. Review generated contracts
   - Add evaluators; set retry_policy

4. Validate
   eva contract validate ./contracts/<name>.yaml

5. Serve
   eva serve --contracts-dir ./contracts

6. Invoke
   POST /v1/contract/invoke  {"contract": "<name>", "body": {...}}
```

---

## File Naming

Output YAML filenames: slashes and dots in the contract name replaced with
underscores.

Example: `weather-agent.get-forecast` → `weather-agent_get-forecast.yaml`.

---

## Notes

- `evaluators` is always empty on import — populate before production use.
- `provider` field is set to the agent/server `name` from the source document;
  update to the actual agent URL before calling `eva serve`.
- Multiple skills/tools → multiple YAML files; each is an independent contract.
