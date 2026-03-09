# Agent Interoperability Protocols
*Research date: 2026-03-09*

## The Three Standards

### Google A2A (Agent2Agent)
- Launched April 2025, now Linux Foundation
- 50+ enterprise partners (Salesforce, SAP, Microsoft, Intuit)
- Core primitive: **Agent Card** (JSON document describing agent capabilities)
- Transport: HTTP, SSE, JSON-RPC
- Matures faster than AGNTCY; broader enterprise deployment
- Spec: https://agent2agent.info/docs/concepts/agentcard/

### Anthropic MCP (Model Context Protocol)
- Most mature: 97M monthly SDK downloads, 10,000+ servers
- Adopted by OpenAI (Mar 2025), Google DeepMind (Apr 2025)
- Focus: model-to-tools/context (not agent-to-agent)
- Now governed by Linux Foundation Agentic AI Foundation
- Spec: https://modelcontextprotocol.io/specification/2025-11-25

### AGNTCY
- Launched March 2025 by Cisco, LangChain, Galileo, Glean
- Linux Foundation governance (July 2025)
- 75+ companies by July 2025, but still prototype/early
- **Key**: designed to be an interoperability layer OVER A2A and MCP
- GitHub: https://github.com/agntcy
- Docs: https://docs.agntcy.org/

## AGNTCY Architecture (What Matters for Eva)

Three sub-specs:

**ACP (Agent Connect Protocol)**
- Standard REST API for invoking/configuring remote agents
- OpenAPI spec: https://spec.acp.agntcy.org/
- Python SDK: `pip install agntcy-acp`
- Agent manifest endpoint exposes: capabilities, input/output JSON Schema, thread state

**OASF (Open Agentic Schema Framework)**
- Extensible schema for describing agent attributes, capabilities, metadata
- OCI-based data model + attribute taxonomies
- Can represent A2A agents, MCP servers, or custom formats
- Schema: https://schema.oasf.agntcy.org/

**SLIM (Secure Low-latency Interactive Messaging)**
- gRPC extension with pub/sub, streaming, fire & forget
- MLS encryption + quantum-safe

## Eva's Protocol Strategy

**Recommended approach: OASF/ACP as native format, adapters for the rest**

Rationale:
- AGNTCY is explicitly designed as the interoperability hub — if Eva aligns here, it gets A2A and MCP compatibility "for free" via AGNTCY adapters
- OASF is extensible: Eva's evaluator metadata, contract rules, and scoring can live as OASF extensions
- ACP gives a standard REST contract interface Eva can implement as its gateway endpoint
- Gaps AGNTCY doesn't cover (behavioral scoring, retry policy, discount caps) = Eva's value-add on top

**What Eva adds on top of AGNTCY:**
- Evaluator registry (built-in + plugin)
- Behavioral contract rules (not just schema, but semantic assertions)
- Retry/self-healing policy enforcement
- Scoring and report persistence

**Adapter surface needed:**
- A2A Agent Cards → OASF (AGNTCY may provide this)
- MCP server manifests → OASF (AGNTCY may provide this)
- Custom/legacy agents → Eva's own YAML contract format → OASF

## Contract Format Decision

Eva should define contracts in YAML (human-readable, version-control friendly) but internally represent as OASF-compatible JSON. Provide:
1. `eva contract init` — generates YAML template
2. `eva contract validate` — validates YAML against OASF schema
3. Import path: A2A AgentCard → Eva YAML → OASF
