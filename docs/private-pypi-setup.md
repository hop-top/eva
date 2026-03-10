# Private PyPI Setup

Eva alpha packages are distributed via a private PyPI proxy hosted on Cloudflare Workers.

**Worker URL:** https://eva-pkg.ideacrafters-llc.workers.dev

Token provisioned via admin API — see [hop-top/eva-pkg](https://github.com/hop-top/eva-pkg).

---

## Install

```sh
pip install eva \
  --index-url https://<token>@eva-pkg.ideacrafters-llc.workers.dev/simple/ \
  --extra-index-url https://pypi.org/simple/
```

Replace `<token>` with the partner token issued by the hop-top team.

---

## Provisioning Partner Tokens

Admin API: https://github.com/hop-top/eva-pkg

```sh
curl -X POST https://eva-pkg.ideacrafters-llc.workers.dev/admin/partners \
  -H "X-Admin-Secret: <secret>" \
  -H "Content-Type: application/json" \
  -d '{"partner": "Acme Corp", "limit": 500}'
```

Response includes `token`, `index_url`, and a ready-to-use `install_hint`.

---

## Upload Packages

Packages are uploaded directly to R2 bucket `eva-private-pypi` by the hop-top team:

```sh
wrangler r2 object put eva-private-pypi/eva/eva-0.1.0a1-py3-none-any.whl \
  --file dist/eva-0.1.0a1-py3-none-any.whl
```

---

## Architecture

- Cloudflare Worker proxies all PyPI requests
- R2 bucket `eva-private-pypi` stores wheel and sdist files
- KV namespace `eva-partners` stores token records with download limits
- Per-request token auth; downloads tracked per partner

Partners never access R2 directly — all traffic goes through the Worker proxy.
