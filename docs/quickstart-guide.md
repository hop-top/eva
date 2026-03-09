# Quickstart Guide — Eva

Get up and running with Eva in under 5 minutes. This guide will walk you through initializing a project, defining a contract, and running your first evaluation.

---

## 1. Installation

Install Eva using your favorite Python package manager.

```bash
pip install eva-core
```

---

## 2. Initialize your project

Run `eva init` in your project's root directory.

```bash
mkdir my-agent-tests
cd my-agent-tests
eva init
```

This will create a basic structure, including an `evals/` directory and an `eva_plugins.py` file.

---

## 3. Define your first contract

Create a contract file in `evals/my_contract.yaml`. This contract will ensure your agent's response contains the word "hello" and is valid JSON.

```yaml
# evals/my_contract.yaml
name: greeting_contract
provider: greeting-agent
request_schema:
  type: object
  required: [name]
evaluators:
  - name: contains
    substring: "hello"
    case_sensitive: false
  - name: json_schema_valid
    schema:
      type: object
      required: [message]
```

---

## 4. Create an evaluation dataset

Create a dataset file in `evals/dataset.yaml`. This specifies the test cases to run.

```yaml
# evals/dataset.yaml
name: greeting_suite
target: http://localhost:8000/chat
tests:
  - id: test_01
    input: '{"name": "World"}'
```

---

## 5. Run the evaluation

Assuming your agent is running at `http://localhost:8000/chat`, run the following command:

```bash
eva run --dataset evals/dataset.yaml
```

Eva will:
1.  Load your dataset and contract.
2.  Send the input to your agent.
3.  Evaluate the response against your contract.
4.  Print a summary of the results to your terminal.

---

## 6. What's Next?

- **Custom Evaluators**: Add a custom check in `eva_plugins.py`.
- **CI/CD Integration**: Add `eva run` to your GitHub Actions or Jenkins pipeline to gate releases.
- **LLM-as-Judge**: In Phase 2, use the `relevance` evaluator to check semantic quality.
