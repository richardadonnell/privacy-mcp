# Privacy MCP Server

A portable Docker-based server that exposes [Privacy.com](https://privacy.com) virtual card and transaction data via two protocols simultaneously:

- **`/mcp`** — FastMCP streamable-HTTP for AI assistants that support the MCP protocol (Claude Desktop, etc.)
- **`/api/*`** — Plain REST endpoints for automation tools like n8n, Zapier, or custom scripts
- **`/health`** — Unauthenticated health check

---

## Getting Started

### Step 1 — Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose installed
- A [Privacy.com](https://privacy.com) account with developer access

### Step 2 — Get your Privacy API key

Get your API key from [Privacy.com Account Settings](https://app.privacy.com/account).

### Step 3 — Generate your MCP API key

This key protects all `/mcp` and `/api/*` endpoints. Generate one now and keep it handy:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output — you'll use it as `MCP_API_KEY` in the next step.

### Step 4 — Configure environment

Copy `.env.example` to `.env` and fill it in:

```env
PRIVACY_API_KEY=your-privacy-api-key-here
MCP_API_KEY=your-generated-key-here
PRIVACY_SANDBOX=false
PORT=8001
```

> For Coolify, set these values in Coolify Secrets instead of committing a real `.env` file.

### Step 5 — Start the server

```bash
docker compose up -d
```

### Step 6 — Verify it's working

```bash
# Health check (no auth needed)
curl http://localhost:8001/health

# Fetch your cards (replace with your MCP_API_KEY)
curl -H "Authorization: Bearer your-generated-key-here" http://localhost:8001/api/cards
```

You should see `{"status": "ok", "sandbox": false}` and a JSON list of your cards. If you do, you're good to go.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `PRIVACY_API_KEY` | ✅ Yes | Your Privacy.com API key from account settings |
| `MCP_API_KEY` | ✅ Yes | Protects all endpoints — generate with `secrets.token_hex(32)` |
| `PRIVACY_SANDBOX` | No | `true` to target `sandbox.privacy.com` instead of production (default: `false`) |
| `PORT` | No | Port to listen on (default: `8001`) |

---

## Coolify Deployment

1. Create a new application in Coolify using this repository.
2. Deploy using Docker Compose.
3. Set environment variables in Coolify Secrets:
   - `PRIVACY_API_KEY`
   - `MCP_API_KEY`
   - `PRIVACY_SANDBOX` (`false` for production, `true` for sandbox)
   - `PORT` (optional, defaults to `8001`)
4. Deploy and verify `https://<your-domain>/health` returns `{"status": "ok"}`.

---

## Claude Desktop MCP Entry

```json
"privacy-com": {
  "command": "uvx",
  "args": ["mcp-proxy", "--transport", "streamablehttp", "http://localhost:8001/mcp"],
  "env": { "API_ACCESS_TOKEN": "YOUR_MCP_API_KEY" }
}
```

---

## REST API Endpoints

All endpoints require: `Authorization: Bearer {MCP_API_KEY}` except `/health`.

---

### `GET /health`

Unauthenticated health check.

```json
{ "status": "ok", "sandbox": false }
```

---

### `GET /api/cards`

Return all virtual cards on the account with optional filtering.

| Parameter | Type | Description |
|---|---|---|
| `begin` | `YYYY-MM-DD` | Filter cards created on or after this date |
| `end` | `YYYY-MM-DD` | Filter cards created on or before this date |
| `page` | integer | Page number (1-indexed) |
| `page_size` | integer | Results per page (default 50, max 50) |

Example:

```bash
curl -H "Authorization: Bearer YOUR_MCP_API_KEY" "http://localhost:8001/api/cards?page=1&page_size=25"
```

---

### `GET /api/cards/{card_token}`

Return details for a single card.

**Path parameter:** `card_token` — the Privacy.com card token

Example:

```bash
curl -H "Authorization: Bearer YOUR_MCP_API_KEY" "http://localhost:8001/api/cards/crd_123"
```

---

### `POST /api/cards`

Create a new virtual card.

**JSON body:**

```json
{
  "type": "SINGLE_USE",
  "memo": "Test card",
  "spend_limit": 1000,
  "spend_limit_duration": "FOREVER",
  "state": "OPEN",
  "funding_token": "fsrc_123"
}
```

| Field | Required | Description |
|---|---|---|
| `type` | ✅ Yes | `SINGLE_USE`, `MERCHANT_LOCKED`, `UNLOCKED`, `DIGITAL_WALLET`, or `PHYSICAL` |
| `memo` | No | Friendly card label |
| `spend_limit` | No | Integer cents (e.g., `1000` = $10.00) |
| `spend_limit_duration` | No | `TRANSACTION`, `MONTHLY`, `ANNUALLY`, or `FOREVER` |
| `state` | No | `OPEN` or `PAUSED` |
| `funding_token` | No | Funding source token |

---

### `PATCH /api/cards/{card_token}`

Update a card's state, memo, or spend limits.

**Path parameter:** `card_token` — the Privacy.com card token

**JSON body** (all fields optional):

```json
{
  "state": "PAUSED",
  "memo": "Paused for testing"
}
```

---

### `GET /api/transactions`

Return transactions across all cards or for a specific card.

| Parameter | Type | Description |
|---|---|---|
| `card_token` | string | Filter to one card |
| `result` | string | `APPROVED` or `DECLINED` |
| `begin` | `YYYY-MM-DD` | Filter on or after date |
| `end` | `YYYY-MM-DD` | Filter on or before date |
| `page` | integer | Page number (1-indexed) |
| `page_size` | integer | Results per page (default 50, max 50) |

Example:

```bash
curl -H "Authorization: Bearer YOUR_MCP_API_KEY" "http://localhost:8001/api/transactions?result=APPROVED&page=1&page_size=50"
```

---

### `GET /api/funding_sources`

Return all linked funding sources.

Example:

```bash
curl -H "Authorization: Bearer YOUR_MCP_API_KEY" "http://localhost:8001/api/funding_sources"
```

---

## MCP Tools

---

### `list_cards`

Return all virtual cards with optional date and pagination filters.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `begin` | `YYYY-MM-DD` | — | Filter cards created on or after this date |
| `end` | `YYYY-MM-DD` | — | Filter cards created on or before this date |
| `page` | integer | `1` | Page number (1-indexed) |
| `page_size` | integer | `50` | Results per page (max 50) |

---

### `get_card`

Return details for one virtual card by token.

| Parameter | Type | Description |
|---|---|---|
| `card_token` | string | The Privacy.com card token |

---

### `create_card`

Create a new virtual card.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `type` | string | ✅ Yes | `SINGLE_USE`, `MERCHANT_LOCKED`, `UNLOCKED`, `DIGITAL_WALLET`, or `PHYSICAL` |
| `memo` | string | No | Friendly card label |
| `spend_limit` | integer | No | Integer cents (e.g., `1000` = $10.00) |
| `spend_limit_duration` | string | No | `TRANSACTION`, `MONTHLY`, `ANNUALLY`, or `FOREVER` |
| `state` | string | No | `OPEN` or `PAUSED` |
| `funding_token` | string | No | Funding source token |

---

### `update_card`

Update a card's state, memo, or spend limits.

| Parameter | Type | Description |
|---|---|---|
| `card_token` | string | The card to update (required) |
| `state` | string | `OPEN` to resume, `PAUSED` to pause, `CLOSED` to permanently close |
| `memo` | string | Updated card label |
| `spend_limit` | integer | New limit in integer cents |
| `spend_limit_duration` | string | `TRANSACTION`, `MONTHLY`, `ANNUALLY`, or `FOREVER` |

---

### `list_transactions`

Return transactions with optional filters.

| Parameter | Type | Description |
|---|---|---|
| `card_token` | string | Filter to one card |
| `result` | string | `APPROVED` or `DECLINED` |
| `begin` | `YYYY-MM-DD` | Filter on or after date |
| `end` | `YYYY-MM-DD` | Filter on or before date |
| `page` | integer | Page number (1-indexed) |
| `page_size` | integer | Results per page (default 50, max 50) |

---

### `list_funding_sources`

Return all linked funding sources.

No parameters.
