"""FreudAgent A2UI MCP Server.

Two modes from one entry point:
    uv run a2ui/server.py --mode stdio    # Claude Desktop (MCP stdio)
    uv run a2ui/server.py --mode http     # Standalone web app (HTTP + SSE)
    uv run a2ui/server.py --mode both     # Both simultaneously
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import threading
from typing import Any

import anyio
import orjson
import mcp.types as types
from mcp.server.lowlevel import Server

from adapter import adapt_v09_to_v08
from bridge import A2UIBridge
from freud_schema.tables import ValidationStatus
from prompt import build_system_prompt, build_user_prompt
from providers import get_a2ui_provider
from queries import (
    get_dashboard_stats,
    get_extraction_detail,
    get_extractions,
    get_feedback_summary,
    get_sessions,
    get_store,
)

# ------------------------------------------------------------------
# Globals
# ------------------------------------------------------------------

_bridge = A2UIBridge()
_store_cache: Any = None
_provider_cache: dict[str, Any] = {}


def _get_store():
    """Return a cached experiment store (one connection for server lifetime)."""
    global _store_cache
    if _store_cache is None:
        _store_cache = get_store()
    return _store_cache


def _get_provider(name: str):
    """Return a cached A2UI provider (providers are stateless after construction)."""
    if name not in _provider_cache:
        _provider_cache[name] = get_a2ui_provider(name)
    return _provider_cache[name]


# ------------------------------------------------------------------
# MCP Tool Definitions
# ------------------------------------------------------------------


def _tool_definitions() -> list[types.Tool]:
    return [
        types.Tool(
            name="render_a2ui",
            description="Validate and return A2UI v0.9 JSON messages. Pass raw A2UI messages for structural validation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "messages": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Array of A2UI v0.9 messages to validate",
                    },
                },
                "required": ["messages"],
            },
        ),
        types.Tool(
            name="compose_surface",
            description=(
                "Generate an A2UI surface using an LLM. The LLM produces v0.9 messages, "
                "which are validated and converted to v0.8 for the Lit renderer. "
                "Any surface type can be requested -- the LLM generates the layout."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "surface": {
                        "type": "string",
                        "description": (
                            "Surface type hint (e.g., 'dashboard', 'extraction_list', "
                            "'extraction_card', 'session_timeline', 'feedback_summary', "
                            "or any free-form description)"
                        ),
                    },
                    "params": {
                        "type": "object",
                        "description": "Surface-specific parameters (e.g., extraction_id, skill_id, limit)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Free-form description of the desired surface layout",
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["claude", "gemini", "echo"],
                        "description": "Which LLM provider to use (default: echo)",
                    },
                },
                "required": ["surface"],
            },
        ),
        types.Tool(
            name="list_extractions",
            description="Query extractions from the FreudAgent experiment database with optional filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "integer", "description": "Filter by skill ID"},
                    "validation_status": {
                        "type": "string",
                        "enum": ["pending", "validated", "rejected"],
                        "description": "Filter by validation status",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 50)"},
                },
            },
        ),
        types.Tool(
            name="show_extraction",
            description="Show a single extraction with full context: source, skill, feedback.",
            inputSchema={
                "type": "object",
                "properties": {
                    "extraction_id": {"type": "integer", "description": "Extraction ID to show"},
                },
                "required": ["extraction_id"],
            },
        ),
        types.Tool(
            name="dashboard",
            description="Summary stats for the FreudAgent experiment harness: skill counts, extraction breakdown, feedback signal, recent sessions.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


# ------------------------------------------------------------------
# Data gathering for compose_surface
# ------------------------------------------------------------------


def _gather_data(store: Any, surface: str, params: dict[str, Any]) -> dict[str, Any]:
    """Gather data from the store based on the surface type."""
    if surface == "dashboard":
        return get_dashboard_stats(store)

    elif surface == "extraction_list":
        return _handle_list_extractions(params)

    elif surface == "extraction_card":
        ext_id = params.get("extraction_id")
        if ext_id is None:
            return {"error": "extraction_id required"}
        detail = get_extraction_detail(store, ext_id)
        return detail or {"error": f"extraction {ext_id} not found"}

    elif surface == "session_timeline":
        sessions = get_sessions(store, limit=params.get("limit", 20))
        return {"sessions": sessions, "count": len(sessions)}

    elif surface == "feedback_summary":
        return get_feedback_summary(store, skill_id=params.get("skill_id"))

    else:
        # Free-form surface: gather everything the LLM might need
        return get_dashboard_stats(store)


# ------------------------------------------------------------------
# Tool Handlers
# ------------------------------------------------------------------


def _handle_render_a2ui(arguments: dict[str, Any]) -> dict[str, Any]:
    messages = arguments.get("messages", [])
    errors = _bridge.validate(messages)
    if errors:
        return {"valid": False, "errors": errors}
    return {"valid": True, "messages": messages}


def _handle_compose_surface(arguments: dict[str, Any]) -> dict[str, Any]:
    surface = arguments.get("surface", "")
    params = arguments.get("params", {})
    provider_name = arguments.get("provider", "echo")
    description = arguments.get("description")

    store = _get_store()
    data = _gather_data(store, surface, params)

    if isinstance(data, dict) and "error" in data:
        return data

    provider = _get_provider(provider_name)
    system = build_system_prompt()  # lru_cache handles caching
    user = build_user_prompt(surface, data, description=description)

    result = provider.generate(system, user)
    messages_v09 = result.messages

    # Validate v0.9 messages
    errors = _bridge.validate(messages_v09)
    if errors:
        return {"valid": False, "errors": errors}

    # Convert to v0.8 for the Lit renderer
    messages_v08 = adapt_v09_to_v08(messages_v09)
    return {
        "valid": True,
        "messages": messages_v08,
        "provider": provider_name,
        "model": result.model,
        "tokens": {
            "input": result.input_tokens,
            "output": result.output_tokens,
        },
    }


def _handle_list_extractions(arguments: dict[str, Any]) -> dict[str, Any]:
    store = _get_store()
    exts = get_extractions(
        store,
        skill_id=arguments.get("skill_id"),
        validation_status=arguments.get("validation_status"),
        limit=arguments.get("limit", 50),
    )
    return {"extractions": exts, "count": len(exts)}


def _handle_show_extraction(arguments: dict[str, Any]) -> dict[str, Any]:
    store = _get_store()
    ext_id = arguments.get("extraction_id")
    if ext_id is None:
        return {"error": "extraction_id is required"}
    detail = get_extraction_detail(store, ext_id)
    if detail is None:
        return {"error": f"extraction {ext_id} not found"}
    return {"extraction": detail}


def _handle_dashboard(arguments: dict[str, Any]) -> dict[str, Any]:
    store = _get_store()
    stats = get_dashboard_stats(store)
    return {"dashboard": stats}


_TOOL_HANDLERS = {
    "render_a2ui": _handle_render_a2ui,
    "compose_surface": _handle_compose_surface,
    "list_extractions": _handle_list_extractions,
    "show_extraction": _handle_show_extraction,
    "dashboard": _handle_dashboard,
}


# ------------------------------------------------------------------
# Action Handlers (for interactivity)
# ------------------------------------------------------------------


def _handle_action(action: dict[str, Any], provider: str = "echo") -> dict[str, Any]:
    """Process a userAction from the web client."""
    name = action.get("name", "")
    context = action.get("context", {})
    store = _get_store()

    if name == "validate_extraction":
        ext_id = context.get("extraction_id")
        if ext_id is not None:
            store.update_validation(ext_id, status=ValidationStatus.VALIDATED, validated_by="a2ui")
            return {"success": True, "action": "validated", "extraction_id": ext_id}

    elif name == "reject_extraction":
        ext_id = context.get("extraction_id")
        if ext_id is not None:
            store.update_validation(ext_id, status=ValidationStatus.REJECTED, validated_by="a2ui")
            return {"success": True, "action": "rejected", "extraction_id": ext_id}

    elif name == "show_extraction":
        ext_id = context.get("extraction_id")
        if ext_id is not None:
            detail = get_extraction_detail(store, ext_id)
            if detail:
                result = _handle_compose_surface({
                    "surface": "extraction_card",
                    "params": {"extraction_id": ext_id},
                    "provider": provider,
                })
                if result.get("valid"):
                    return {"success": True, "messages": result["messages"]}

    return {"success": False, "error": f"unknown action: {name}"}


# ------------------------------------------------------------------
# MCP Server Setup
# ------------------------------------------------------------------


def create_mcp_server() -> Server:
    app = Server("freudagent-a2ui")

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return _tool_definitions()

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

        result = handler(arguments)
        text = orjson.dumps(result, option=orjson.OPT_INDENT_2).decode()
        return [types.TextContent(type="text", text=text)]

    return app


# ------------------------------------------------------------------
# stdio Mode
# ------------------------------------------------------------------


async def run_stdio(app: Server) -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())


# ------------------------------------------------------------------
# HTTP Mode (Starlette + SSE)
# ------------------------------------------------------------------


def create_http_app(mcp_app: Server) -> Any:
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Mount, Route
    from starlette.staticfiles import StaticFiles

    static_dir = pathlib.Path(__file__).parent / "static"

    async def action(request: Request) -> Response:
        body = await request.body()
        action_data = orjson.loads(body)
        user_action = action_data.get("action", action_data)
        provider = action_data.get("provider", "echo")
        result = _handle_action(user_action, provider=provider)
        return JSONResponse(result)

    async def api_extractions(request: Request) -> Response:
        store = _get_store()
        skill_id = request.query_params.get("skill_id")
        validation_status = request.query_params.get("validation_status")
        limit = int(request.query_params.get("limit", "50"))

        exts = get_extractions(
            store,
            skill_id=int(skill_id) if skill_id else None,
            validation_status=validation_status,
            limit=limit,
        )
        data = orjson.dumps(exts).decode()
        return Response(content=data, media_type="application/json")

    async def api_compose(request: Request) -> Response:
        """REST endpoint that composes a surface and returns A2UI messages."""
        body = await request.body()
        args = orjson.loads(body)
        result = _handle_compose_surface(args)
        data = orjson.dumps(result).decode()
        return Response(content=data, media_type="application/json")

    async def api_dashboard(request: Request) -> Response:
        store = _get_store()
        stats = get_dashboard_stats(store)
        data = orjson.dumps(stats).decode()
        return Response(content=data, media_type="application/json")

    routes = [
        Route("/action", endpoint=action, methods=["POST"]),
        Route("/api/extractions", endpoint=api_extractions),
        Route("/api/compose", endpoint=api_compose, methods=["POST"]),
        Route("/api/dashboard", endpoint=api_dashboard),
    ]

    # Serve built Lit app as static files (SPA catch-all)
    if static_dir.exists():
        routes.append(Mount("/", app=StaticFiles(directory=str(static_dir), html=True)))

    return Starlette(
        debug=True,
        routes=routes,
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            ),
        ],
    )


# ------------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="FreudAgent A2UI Server")
    parser.add_argument(
        "--mode",
        choices=["stdio", "http", "both"],
        default="http",
        help="Server mode (default: http)",
    )
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (default: 127.0.0.1)")
    args = parser.parse_args()

    mcp_app = create_mcp_server()

    if args.mode == "stdio":
        print("FreudAgent A2UI server starting (stdio mode)", file=sys.stderr)
        anyio.run(run_stdio, mcp_app)

    elif args.mode == "http":
        import uvicorn

        http_app = create_http_app(mcp_app)
        print(f"FreudAgent A2UI server starting at http://{args.host}:{args.port}", file=sys.stderr)
        uvicorn.run(http_app, host=args.host, port=args.port)

    elif args.mode == "both":
        import uvicorn

        http_app = create_http_app(mcp_app)

        # Run stdio in a background thread
        def stdio_thread():
            anyio.run(run_stdio, mcp_app)

        thread = threading.Thread(target=stdio_thread, daemon=True)
        thread.start()

        print(f"FreudAgent A2UI server starting at http://{args.host}:{args.port} (+ stdio)", file=sys.stderr)
        uvicorn.run(http_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
