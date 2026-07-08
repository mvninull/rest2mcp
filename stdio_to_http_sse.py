#!/usr/bin/env python3
"""
stdio_to_http_sse.py — Bridge stdio MCP servers to HTTP/SSE (FastMCP v3).

Wraps any stdio-based MCP server (uvx, npx, pipx, etc.) and serves it
over HTTP/SSE using FastMCP's create_proxy().

Usage:
  python stdio_to_http_sse.py --command uvx --args mcp-excel-server
  python stdio_to_http_sse.py --command npx --args @modelcontextprotocol/server-filesystem .
  python stdio_to_http_sse.py --command pipx --args mcp-server-sqlite --port 8766
  python stdio_to_http_sse.py --config server.json
  python stdio_to_http_sse.py --config claude_desktop_config.json --name excel

Equivalente via FastMCP CLI directamente:
  fastmcp run config.json --transport sse --port PORT --host HOST
  fastmcp run <(echo '{"mcpServers":{"srv":{"command":"uvx","args":["mcp-excel-server"]}}}') --transport sse

Integration with merge-point:
  POST /v1/servers/merge
  { "source_server_id": "srv_abc123",
    "remote_url": "http://localhost:8765/sse",
    "namespace": "excel",
    "merged_name": "Merged Excel + Loja" }
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile


def _build_config(command: str, cmd_args: list[str], env_vars: dict[str, str], server_name: str) -> dict:
    cfg = {
        "mcpServers": {
            server_name: {
                "command": command,
                "args": cmd_args,
            }
        }
    }
    if env_vars:
        cfg["mcpServers"][server_name]["env"] = env_vars
    return cfg


def _resolve_config(args: argparse.Namespace) -> tuple[str, list[str], dict[str, str], str]:
    command = args.command
    cmd_args = list(args.args)
    env_vars: dict[str, str] = {}
    server_name = args.name

    for e in args.env:
        if "=" in e:
            k, v = e.split("=", 1)
            env_vars[k] = v

    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg = json.load(f)
        servers = cfg.get("mcpServers") or {}
        if servers:
            names = list(servers.keys())
            chosen = names[0]
            sv = servers[chosen]
            command = sv.get("command") or command
            cmd_args = sv.get("args") or cmd_args
            env_vars = {**env_vars, **sv.get("env", {})}
            if not server_name:
                server_name = chosen
        else:
            command = cfg.get("command") or command
            cmd_args = cfg.get("args") or cmd_args
            env_vars = {**env_vars, **cfg.get("env", {})}

    if not command:
        print("Error: --command ou --config é obrigatório")
        sys.exit(1)

    if not server_name:
        server_name = f"bridged-{os.path.basename(command)}"

    return command, cmd_args, env_vars, server_name


def main():
    parser = argparse.ArgumentParser(
        description="Bridge stdio MCP servers to HTTP/SSE para merge-point (FastMCP v3)"
    )
    parser.add_argument("--command", "-c", help="Command (uvx, npx, pipx, etc.)")
    parser.add_argument("--args", "-a", nargs="*", default=[], help="Args for the command")
    parser.add_argument("--env", "-e", nargs="*", default=[], help="Env vars KEY=VALUE")
    parser.add_argument("--port", "-p", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--config", "-f", help="JSON config file")
    parser.add_argument("--name", "-n", help="Server name for mcpServers config")
    parser.add_argument(
        "--transport", "-t", choices=["sse", "http"], default="sse",
        help="Transport: sse (default) ou http (Streamable HTTP)"
    )

    args = parser.parse_args()
    command, cmd_args, env_vars, server_name = _resolve_config(args)
    config = _build_config(command, cmd_args, env_vars, server_name)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="fastmcp_bridge_", delete=False, encoding="utf-8"
    ) as f:
        json.dump(config, f)
        config_path = f.name

    cmd = [
        sys.executable, "-m", "fastmcp", "run", config_path,
        "--transport", args.transport,
        "--host", args.host,
        "--port", str(args.port),
    ]

    print(f"Starting: {command} {' '.join(cmd_args)}")
    print(f"Server:   {server_name}")
    print(f"Running: {' '.join(cmd)}")
    print(f"Serving on http://{args.host}:{args.port}/{args.transport}")
    print("Press Ctrl+C to stop")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            os.unlink(config_path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
