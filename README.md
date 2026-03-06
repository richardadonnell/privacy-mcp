# privacy-mcp

Privacy.com MCP server exposing both FastMCP (`/mcp`) and REST (`/api/*`) endpoints.

## Features

- FastMCP tools for cards, transactions, funding sources, and recent webhook events
- REST endpoints for n8n compatibility
- Bearer auth protection for `/mcp` and `/api/*`
- HMAC verification for Privacy.com transaction webhooks
- Docker and docker-compose deployment support

## Getting Started

### Step 1 - Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose installed
- A [Privacy.com](https://privacy.com) account with developer access

### Step 2 - Get your Privacy API key

Get your API key from [Privacy.com Account Settings](https://app.privacy.com/account).

### Step 3 - Generate your MCP API key

This key protects all `/mcp` and `/api/*` endpoints:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Step 4 - Configure environment

Copy `.env.example` to `.env` and set:

- `PRIVACY_API_KEY`
- `MCP_API_KEY`
- `PRIVACY_SANDBOX` (`true` or `false`)
- `PORT` (defaults to `8001` to avoid colliding with monarch-mcp)

For Coolify, set these values in Coolify Secrets instead of committing a real `.env` file.

### Step 5 - Run locally

```bash
docker compose up --build
```

Health check:

```bash
curl http://localhost:8001/health
```

## Coolify Deployment

1. Create a new application in Coolify using this repository.
2. Deploy using Docker Compose.
3. Set environment variables in Coolify Secrets:
   - `PRIVACY_API_KEY`
   - `MCP_API_KEY`
   - `PRIVACY_SANDBOX` (`false` for production, `true` for sandbox)
   - `PORT` (optional, defaults to `8001`)
4. Deploy and verify `https://<your-domain>/health` returns `{"status": "ok"}`.
5. Configure Privacy webhook URL to `https://<your-domain>/webhook/transaction`.

## Claude Desktop MCP Entry

```json
"privacy-com": {
  "command": "uvx",
  "args": ["mcp-proxy", "--transport", "streamablehttp", "http://localhost:8001/mcp"],
  "env": { "API_ACCESS_TOKEN": "YOUR_MCP_API_KEY" }
}
```

## REST API Endpoints

All endpoints require: `Authorization: Bearer {MCP_API_KEY}` except `/health` and `/webhook/transaction`.

### `GET /health`

Unauthenticated health check.

```json
{ "status": "ok", "sandbox": false }
```

### `POST /webhook/transaction`

Unauthenticated webhook receiver for Privacy.com transaction events.

- Header: `X-Privacy-HMAC`
- Body: JSON webhook event payload from Privacy.com

The server verifies the HMAC signature and stores up to the most recent 100 events in memory.

### `GET /api/cards`

Return all virtual cards on the account with optional filtering.

| Parameter | Type | Description |
| --- | --- | --- |
| `begin` | `YYYY-MM-DD` | Filter cards created on or after this date |
| `end` | `YYYY-MM-DD` | Filter cards created on or before this date |
| `page` | integer | Page number (1-indexed) |
| `page_size` | integer | Results per page (default 50, max 50) |

Example:

```bash
curl -H "Authorization: Bearer YOUR_MCP_API_KEY" "http://localhost:8001/api/cards?page=1&page_size=25"
```

### `GET /api/cards/{card_token}`

Return details for a single card.

- Path param: `card_token` (required)

Example:

```bash
curl -H "Authorization: Bearer YOUR_MCP_API_KEY" "http://localhost:8001/api/cards/crd_123"
```

### `POST /api/cards`

Create a new virtual card.

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

Fields:

| Field | Required | Description |
| --- | --- | --- |
| `type` | Yes | `SINGLE_USE`, `MERCHANT_LOCKED`, `UNLOCKED`, `DIGITAL_WALLET`, or `PHYSICAL` |
| `memo` | No | Friendly card label |
| `spend_limit` | No | Integer cents (e.g., `1000` = $10.00) |
| `spend_limit_duration` | No | `TRANSACTION`, `MONTHLY`, `ANNUALLY`, or `FOREVER` |
| `state` | No | `OPEN` or `PAUSED` |
| `funding_token` | No | Funding source token |

### `PATCH /api/cards/{card_token}`

Update a card's state, memo, or spend limits.

- Path param: `card_token` (required)

```json
{
  "state": "PAUSED",
  "memo": "Paused for testing"
}
```

### `GET /api/transactions`

Return transactions across all cards or for a specific card.

| Parameter | Type | Description |
| --- | --- | --- |
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

### `GET /api/funding_sources`

Return all linked funding sources.

Example:

```bash
curl -H "Authorization: Bearer YOUR_MCP_API_KEY" "http://localhost:8001/api/funding_sources"
```

### `GET /api/webhooks/recent`

Return the most recent webhook events stored in-memory.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `limit` | integer | 20 | Number of events to return (max 100) |

Example:

```bash
curl -H "Authorization: Bearer YOUR_MCP_API_KEY" "http://localhost:8001/api/webhooks/recent?limit=10"
```

## MCP Tools

These are the MCP tools exposed on `/mcp` for Claude Desktop and other MCP-compatible AI assistants.

### `list_cards(begin, end, page, page_size)`

Return all virtual cards with optional date/pagination filters.

### `get_card(card_token)`

Return details for one virtual card by token.

### `create_card(type, memo, spend_limit, spend_limit_duration, state, funding_token)`

Create a virtual card.

- `type` is required
- Amounts are integer cents

### `update_card(card_token, state, memo, spend_limit, spend_limit_duration)`

Update card state or limits.

- Use `state=PAUSED` to pause
- Use `state=OPEN` to resume
- Use `state=CLOSED` to permanently close

### `list_transactions(card_token, result, begin, end, page, page_size)`

Return transactions with optional filters.

### `list_funding_sources()`

Return all linked funding sources.

### `get_recent_webhook_events(limit=20)`

Return the most recent buffered webhook events (max 100).

## Usage Notes

- Outbound Privacy API auth uses `Authorization: api-key <PRIVACY_API_KEY>`.
- Inbound auth to this server uses `Authorization: Bearer <MCP_API_KEY>`.
- `PRIVACY_SANDBOX=true` switches base URL to `https://sandbox.privacy.com/v1`.
- Webhook HMAC is computed over sorted, compact JSON using your Privacy API key as the secret.
