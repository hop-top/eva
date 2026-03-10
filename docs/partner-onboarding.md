# Partner Onboarding

Getting design partners up and running with Eva.

---

## Prerequisites

- Python 3.10+
- `pip` 23+
- Partner token (provided by hop-top team)

Token provided by hop-top team. Contact eva@hop.top to request access.

---

## Install Eva

```sh
pip install eva \
  --index-url https://<your-token>@eva-pkg.ideacrafters-llc.workers.dev/simple/ \
  --extra-index-url https://pypi.org/simple/
```

Replace `<your-token>` with the token provided by the hop-top team.

Verify:

```sh
eva --version
```

---

## Quick Start

1. Create a contract file:

```yaml
# contracts/my-agent.yaml
name: my-agent
version: "1.0"
model: gpt-4o
system_prompt: "You are a helpful assistant."
```

2. Run the gateway:

```sh
eva serve --contracts-dir ./contracts
```

3. Invoke your agent:

```sh
curl -X POST http://localhost:8080/v1/contract/invoke \
  -H "Content-Type: application/json" \
  -d '{"contract": "my-agent", "messages": [{"role": "user", "content": "Hello"}]}'
```

---

## Support

- Docs: https://github.com/hop-top/eva
- Issues: eva@hop.top
- Token issues or access requests: eva@hop.top
