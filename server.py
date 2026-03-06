"""
Privacy.com MCP Server
======================
Dual-protocol server:
  - /mcp          FastMCP streamable-HTTP (for Claude Desktop / Allen)
  - /api/*        Plain REST endpoints (for n8n HTTP Request nodes)
  - /health       Unauthenticated health check
  - /webhook/*    Unauthenticated webhook receiver (Privacy.com posts here)

Auth (inbound):  Authorization: Bearer {MCP_API_KEY} on /mcp and /api/*
Auth (outbound): Authorization: api-key {PRIVACY_API_KEY} on all Privacy.com requests

Env vars:
  PRIVACY_API_KEY   required; Privacy.com API key — also used as HMAC secret for webhooks
  PRIVACY_SANDBOX   optional; set to "true" to hit sandbox.privacy.com instead of api.privacy.com
  MCP_API_KEY       required; protects all /mcp and /api/* endpoints
  PORT              optional, defaults to 8000
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from collections import deque
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
import uvicorn
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("privacy_mcp")

# --- Config ------------------------------------------------------------------

MCP_API_KEY: str = os.environ["MCP_API_KEY"]           # required
PRIVACY_API_KEY: str = os.environ["PRIVACY_API_KEY"]   # required
PRIVACY_SANDBOX: bool = os.getenv("PRIVACY_SANDBOX", "false").lower() == "true"
PORT: int = int(os.getenv("PORT", "8000"))

BASE_URL = (
    "https://sandbox.privacy.com/v1"
    if PRIVACY_SANDBOX
    else "https://api.privacy.com/v1"
)

# --- Privacy.com HTTP client -------------------------------------------------

# Shared async client — reused across requests; created at startup
_privacy_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    if _privacy_client is None:
        raise RuntimeError("Privacy.com client not initialized")
    return _privacy_client


def _json(data: Any) -> str:
    return json.dumps(data, default=str, indent=2)


# --- Webhook event buffer ----------------------------------------------------

_webhook_events: deque[dict] = deque(maxlen=100)


# --- FastMCP instance --------------------------------------------------------

mcp = FastMCP(
    "privacy_com_mcp",
    instructions=(
        "Tools for managing Privacy.com virtual cards, transactions, and funding sources. "
        "Use these tools to create single-use or merchant-locked cards, set spend limits, "
        "pause or close cards, and review transaction history. "
        "Amounts are always in cents (e.g., 1000 = $10.00). "
        "Dates are ISO 8601 (YYYY-MM-DD). "
        "Card types: SINGLE_USE (auto-closes after first charge), MERCHANT_LOCKED (locks to first merchant), "
        "UNLOCKED (any merchant, any amount up to limit). "
        "Card states: OPEN, PAUSED (blocks new charges), CLOSED (permanent). "
        "Spend limit durations: TRANSACTION, MONTHLY, ANNUALLY, FOREVER."
    ),
)

# --- MCP Tools ---------------------------------------------------------------


@mcp.tool(
    name="list_cards",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def list_cards(
    begin: Optional[str] = None,
    end: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
) -> str:
    """
    Return all virtual cards on the account.

    Args:
        begin: Filter cards created on or after this date (YYYY-MM-DD).
        end: Filter cards created on or before this date (YYYY-MM-DD).
        page: Page number (1-indexed) for pagination.
        page_size: Number of results per page (default 50, max 50).
    """
    params: dict[str, Any] = {}
    for k, v in {"begin": begin, "end": end, "page": page, "page_size": page_size}.items():
        if v is not None:
            params[k] = v
    resp = await get_client().get("/cards", params=params)
    resp.raise_for_status()
    return _json(resp.json())


@mcp.tool(
    name="get_card",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def get_card(card_token: str) -> str:
    """
    Return details for a single virtual card.

    Args:
        card_token: The unique card token (from list_cards).
    """
    resp = await get_client().get(f"/cards/{card_token}")
    resp.raise_for_status()
    return _json(resp.json())


@mcp.tool(
    name="create_card",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def create_card(
    type: str,
    memo: Optional[str] = None,
    spend_limit: Optional[int] = None,
    spend_limit_duration: Optional[str] = None,
    state: Optional[str] = None,
    funding_token: Optional[str] = None,
) -> str:
    """
    Create a new virtual card (requires Issuing access).

    Args:
        type: Card type — SINGLE_USE, MERCHANT_LOCKED, UNLOCKED, DIGITAL_WALLET, or PHYSICAL.
        memo: Friendly label for the card (e.g., "Netflix subscription").
        spend_limit: Maximum spend in cents (e.g., 1000 = $10.00). 0 = no limit.
        spend_limit_duration: When the limit resets — TRANSACTION, MONTHLY, ANNUALLY, or FOREVER.
        state: Initial state — OPEN or PAUSED.
        funding_token: Funding source token to charge (from list_funding_sources). Defaults to primary.
    """
    body: dict[str, Any] = {"type": type}
    for k, v in {
        "memo": memo,
        "spend_limit": spend_limit,
        "spend_limit_duration": spend_limit_duration,
        "state": state,
        "funding_token": funding_token,
    }.items():
        if v is not None:
            body[k] = v
    resp = await get_client().post("/cards", json=body)
    resp.raise_for_status()
    return _json(resp.json())


@mcp.tool(
    name="update_card",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
async def update_card(
    card_token: str,
    state: Optional[str] = None,
    memo: Optional[str] = None,
    spend_limit: Optional[int] = None,
    spend_limit_duration: Optional[str] = None,
) -> str:
    """
    Update an existing virtual card — pause, resume, close, or change limits.

    Args:
        card_token: The card token to update.
        state: New state — OPEN (resume), PAUSED (block new charges), or CLOSED (permanent).
        memo: Update the card label.
        spend_limit: New spend limit in cents. 0 = no limit.
        spend_limit_duration: New limit reset period — TRANSACTION, MONTHLY, ANNUALLY, or FOREVER.
    """
    body: dict[str, Any] = {}
    for k, v in {
        "state": state,
        "memo": memo,
        "spend_limit": spend_limit,
        "spend_limit_duration": spend_limit_duration,
    }.items():
        if v is not None:
            body[k] = v
    if not body:
        return _json({"error": "No fields to update — provide at least one of: state, memo, spend_limit, spend_limit_duration"})
    resp = await get_client().patch(f"/cards/{card_token}", json=body)
    resp.raise_for_status()
    return _json(resp.json())


@mcp.tool(
    name="list_transactions",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def list_transactions(
    card_token: Optional[str] = None,
    result: Optional[str] = None,
    begin: Optional[str] = None,
    end: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
) -> str:
    """
    Return transactions across all cards or for a specific card.

    Args:
        card_token: Filter to a specific card token (optional — omit for all cards).
        result: Filter by result — APPROVED or DECLINED.
        begin: Filter transactions on or after this date (YYYY-MM-DD).
        end: Filter transactions on or before this date (YYYY-MM-DD).
        page: Page number (1-indexed).
        page_size: Results per page (default 50, max 50).
    """
    params: dict[str, Any] = {}
    for k, v in {
        "card_token": card_token,
        "result": result,
        "begin": begin,
        "end": end,
        "page": page,
        "page_size": page_size,
    }.items():
        if v is not None:
            params[k] = v
    resp = await get_client().get("/transactions", params=params)
    resp.raise_for_status()
    return _json(resp.json())


@mcp.tool(
    name="list_funding_sources",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def list_funding_sources() -> str:
    """Return all funding sources (bank accounts) linked to the Privacy.com account."""
    resp = await get_client().get("/funding_sources")
    resp.raise_for_status()
    return _json(resp.json())


@mcp.tool(
    name="get_recent_webhook_events",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def get_recent_webhook_events(limit: int = 20) -> str:
    """
    Return the most recent webhook events received from Privacy.com.
    Events are stored in-memory; buffer holds up to 100 events.

    Args:
        limit: Number of recent events to return (max 100, default 20).
    """
    limit = min(limit, 100)
    events = list(_webhook_events)[-limit:]
    return _json({"count": len(events), "events": events})


# --- Auth Middleware ----------------------------------------------------------


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Health check and webhook receiver are public (no Bearer required)
        if path == "/health" or path.startswith("/webhook/"):
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not (auth.startswith("Bearer ") and auth[7:] == MCP_API_KEY):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


# --- Webhook HMAC verification -----------------------------------------------


def _verify_privacy_hmac(body: bytes, hmac_header: str) -> bool:
    """
    Verify the X-Privacy-HMAC header from a Privacy.com webhook.

    Privacy.com computes: HMAC-SHA256(sorted_compact_json, api_key) then base64-encodes it.
    The body must be sorted compact JSON (no extra whitespace).
    """
    try:
        # Privacy signs sorted, compact JSON. Normalize body before computing HMAC.
        payload_obj = json.loads(body)
        canonical = json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()

        secret = PRIVACY_API_KEY.encode()
        expected = base64.b64encode(
            hmac.new(secret, canonical, hashlib.sha256).digest()
        ).decode()
        return hmac.compare_digest(expected, hmac_header)
    except Exception:
        return False


# --- REST Route Handlers -----------------------------------------------------


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "sandbox": PRIVACY_SANDBOX})


async def api_cards(request: Request) -> JSONResponse:
    try:
        params = dict(request.query_params)
        resp = await get_client().get("/cards", params=params)
        resp.raise_for_status()
        return JSONResponse(resp.json())
    except httpx.HTTPStatusError as exc:
        return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
    except Exception as exc:
        logger.error("api_cards: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_card_detail(request: Request) -> JSONResponse:
    try:
        card_token = request.path_params["card_token"]
        resp = await get_client().get(f"/cards/{card_token}")
        resp.raise_for_status()
        return JSONResponse(resp.json())
    except httpx.HTTPStatusError as exc:
        return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
    except Exception as exc:
        logger.error("api_card_detail: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_create_card(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        resp = await get_client().post("/cards", json=body)
        resp.raise_for_status()
        return JSONResponse(resp.json(), status_code=201)
    except httpx.HTTPStatusError as exc:
        return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
    except Exception as exc:
        logger.error("api_create_card: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_update_card(request: Request) -> JSONResponse:
    try:
        card_token = request.path_params["card_token"]
        body = await request.json()
        resp = await get_client().patch(f"/cards/{card_token}", json=body)
        resp.raise_for_status()
        return JSONResponse(resp.json())
    except httpx.HTTPStatusError as exc:
        return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
    except Exception as exc:
        logger.error("api_update_card: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_transactions(request: Request) -> JSONResponse:
    try:
        params = dict(request.query_params)
        resp = await get_client().get("/transactions", params=params)
        resp.raise_for_status()
        return JSONResponse(resp.json())
    except httpx.HTTPStatusError as exc:
        return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
    except Exception as exc:
        logger.error("api_transactions: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_funding_sources(request: Request) -> JSONResponse:
    try:
        resp = await get_client().get("/funding_sources")
        resp.raise_for_status()
        return JSONResponse(resp.json())
    except httpx.HTTPStatusError as exc:
        return JSONResponse({"error": exc.response.text}, status_code=exc.response.status_code)
    except Exception as exc:
        logger.error("api_funding_sources: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_webhooks_recent(request: Request) -> JSONResponse:
    try:
        limit = int(request.query_params.get("limit", 20))
        limit = min(limit, 100)
        events = list(_webhook_events)[-limit:]
        return JSONResponse({"count": len(events), "events": events})
    except Exception as exc:
        logger.error("api_webhooks_recent: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


async def webhook_transaction(request: Request) -> JSONResponse:
    """
    Receive transaction webhook events from Privacy.com.
    Privacy.com sends a POST with JSON body and X-Privacy-HMAC header.
    Returns 200 immediately; Privacy.com retries with exponential backoff on non-200.
    """
    try:
        body = await request.body()
        hmac_header = request.headers.get("X-Privacy-HMAC", "")

        if not _verify_privacy_hmac(body, hmac_header):
            logger.warning("Webhook HMAC verification failed")
            return JSONResponse({"error": "Invalid HMAC"}, status_code=401)

        event = json.loads(body)
        _webhook_events.append(event)
        logger.info(
            "Webhook received: type=%s card=%s",
            event.get("event_type", "unknown"),
            event.get("card", {}).get("token", "unknown"),
        )
        return JSONResponse({"status": "ok"})
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    except Exception as exc:
        logger.error("webhook_transaction: %s", exc)
        # Return 200 anyway so Privacy.com doesn't keep retrying a server error
        return JSONResponse({"status": "error", "detail": str(exc)})


# --- App Assembly ------------------------------------------------------------

mcp_asgi = mcp.http_app()


@asynccontextmanager
async def lifespan(app: Starlette):
    global _privacy_client
    _privacy_client = httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"api-key {PRIVACY_API_KEY}"},
        timeout=30.0,
    )
    logger.info("Privacy.com client initialized (sandbox=%s, base_url=%s)", PRIVACY_SANDBOX, BASE_URL)
    async with mcp_asgi.lifespan(app):
        yield
    await _privacy_client.aclose()
    logger.info("Privacy.com client closed")


app = Starlette(
    routes=[
        Route("/health", endpoint=health, methods=["GET"]),
        # Webhook receiver — public (Privacy.com posts directly; no Bearer)
        Route("/webhook/transaction", endpoint=webhook_transaction, methods=["POST"]),
        # REST endpoints for n8n
        Route("/api/cards", endpoint=api_cards, methods=["GET"]),
        Route("/api/cards/{card_token:str}", endpoint=api_card_detail, methods=["GET"]),
        Route("/api/cards", endpoint=api_create_card, methods=["POST"]),
        Route("/api/cards/{card_token:str}", endpoint=api_update_card, methods=["PATCH"]),
        Route("/api/transactions", endpoint=api_transactions, methods=["GET"]),
        Route("/api/funding_sources", endpoint=api_funding_sources, methods=["GET"]),
        Route("/api/webhooks/recent", endpoint=api_webhooks_recent, methods=["GET"]),
        # FastMCP MCP protocol — handles /mcp
        Mount("/", app=mcp_asgi),
    ],
    lifespan=lifespan,
)

app.add_middleware(APIKeyMiddleware)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
