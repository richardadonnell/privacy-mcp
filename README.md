# privacy-mcp

Privacy.com MCP server exposing both FastMCP (`/mcp`) and REST (`/api/*`) endpoints.

## Features

- FastMCP tools for cards, transactions, funding sources, and recent webhook events
- REST endpoints for n8n compatibility
- Bearer auth protection for `/mcp` and `/api/*`
- HMAC verification for Privacy.com transaction webhooks
- Docker and docker-compose deployment support

## Environment

Copy `.env.example` to `.env` and set:

- `PRIVACY_API_KEY`
- `MCP_API_KEY`
- `PRIVACY_SANDBOX` (`true` or `false`)
- `PORT` (host mapping; defaults to `8001`)

## Run

```bash
docker compose up --build
```

Health check:

```bash
curl http://localhost:8001/health
```
