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

Get your API key from [Privacy Developer Settings](https://privacy.com/account/developer).

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
