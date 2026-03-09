# Concepts Guide — Eva

Eva is an enforcement layer for AI agent behavior. It provides a standardized way to define, evaluate, and enforce "contracts" between AI agents and their consumers.

This guide explains the core concepts of the Eva ecosystem.

---

## 1. Contracts

A **Contract** is the central primitive in Eva. It defines the expected behavior, schemas, and quality standards for an AI agent's interactions.

In Eva, a contract is typically defined in a human-readable **YAML** file.

### Key Components of a Contract:
- **Identity**: Name of the contract, the provider (agent), and the consumer.
- **Request Schema**: A JSON Schema that the incoming request must satisfy.
- **Evaluators**: A list of semantic assertions (tests) that the agent's response must pass.
- **Retry Policy**: Instructions on how to handle failures, including max retries and "hints" to help the agent self-correct.

Contracts act as the "source of truth" for both local development (evaluations) and production enforcement (gateway).

---

## 2. Evaluators

**Evaluators** are the "tests" that Eva runs against an agent's response. They analyze the output and return a **Score**.

### Evaluator Tiers:
1.  **Tier 1 (Deterministic)**: Fast, local, and cost-effective. These use logic like regex, JSON Schema validation, substring matching, or PII detection. No LLM calls are involved.
2.  **Tier 2 (LLM-as-Judge)**: Use a language model (the "Judge") to evaluate semantic qualities like relevance, tone, hallucination, or safety.
3.  **Tier 3 (Custom)**: User-defined evaluators implemented as Python code via the plugin system.

### Scoring Modes:
Every evaluator in a contract can operate in one of three modes:
- **Binary**: Pass (1.0) or Fail (0.0).
- **Threshold**: Passes if the score is greater than or equal to a defined `min_score`.
- **Warn**: Always passes, but logs the score and any reasons for lower quality. Used for monitoring without gating.

---

## 3. Datasets

A **Dataset** is a collection of test cases used to evaluate an agent against a contract.

- **Test Case**: Includes an `input` (the prompt/request) and optionally an `expected_output` or specific `metadata`.
- **Target**: The URL or endpoint of the agent being tested.

Datasets can be defined in **YAML** (developer-friendly) or **JSONL** (data-science friendly) formats.

---

## 4. The Runner

The **Runner** is the engine that executes evaluations. It:
1.  Loads a **Dataset** and a **Contract**.
2.  Calls the target agent for each test case.
3.  Invokes the configured **Evaluators** for each response.
4.  Collects **Results** and computes an overall **Run** score.
5.  Persists the results to a **Storage Adapter**.

The Runner supports async concurrency to speed up large evaluation suites.

---

## 5. Storage and State Adapters

Eva is designed to be pluggable and environment-agnostic.

- **Storage Adapter**: Persists evaluation results (`Runs` and `Results`). Default is **SQLite**.
- **State Adapter**: Manages ephemeral state like distributed locks or rate limits. Default is **Redis**.

In Phase 1, the SQLite adapter is used for local result persistence.

---

## 6. Plugins

Eva uses a powerful plugin system based on `pluggy`. This allows developers to extend Eva with:
- Custom **Evaluators**.
- New **Storage** or **State** backends.
- Custom **OTEL** exporters.

Plugins can be defined locally in an `eva_plugins.py` file for a specific project or packaged as Python libraries and installed via `entry_points`.

---

## 7. AGNTCY and Protocols

Eva is built with interoperability in mind. It aligns with the **AGNTCY** protocol (OASF and ACP standards) to ensure it can work with any agent that follows industry standards like **A2A** (Agent2Agent) or **MCP** (Model Context Protocol).

Internally, Eva's contracts are compatible with OASF (Open Agentic Schema Framework), making it the "connective tissue" for a multi-agent ecosystem.
