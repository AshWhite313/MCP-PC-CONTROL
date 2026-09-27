"""Entry point: ``mcp-pc-control`` / ``python -m pc_control`` (stdio transport)."""

from __future__ import annotations

import argparse
import logging
import sys

from pc_control.config import load_config
from pc_control.core.errors import ToolError
from pc_control.platform.factory import create_backend
from pc_control.security.audit import verify_chain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcp-pc-control", description=__doc__)
    parser.add_argument("--policy", help="Path to a policy TOML file (see config/policy.default.toml).")
    parser.add_argument("--backend", default="auto", choices=["auto", "windows", "fake"])
    parser.add_argument("--level", choices=["observe", "interact", "operate", "full"],
                        help="Override the permission level from the policy.")
    parser.add_argument("--profile", choices=["observe", "desktop", "full"], help="Override the tool profile.")
    parser.add_argument("--verify-audit", metavar="FILE", help="Verify an audit log hash chain and exit.")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    # stdout carries the MCP protocol: logs must go to stderr.
    logging.basicConfig(stream=sys.stderr, level=args.log_level.upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.verify_audit:
        from pathlib import Path

        report = verify_chain(Path(args.verify_audit))
        print(report)
        return 0 if report.ok else 1

    config = load_config(args.policy)
    if args.level:
        config.general.level = args.level
    if args.profile:
        config.general.profile = args.profile
    try:
        backend = create_backend(args.backend)
    except ToolError as e:
        print(e.message, file=sys.stderr)
        return 2

    from pc_control.server import build_server

    server, rt, _ = build_server(config, backend)
    if backend.start_services is not None:
        backend.start_services(killswitch=rt.killswitch, hotkey=config.limits.killswitch_hotkey)
    server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
