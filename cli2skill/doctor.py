"""cli2skill doctor — audit Claude Code MCP routing chain for drift.

Reads the three-layer Claude Code config:
  1. ~/.claude.json -- mcpServers (global + per-project) + disabledMcpServers
  2. ~/.claude/settings.{json,local.json} -- enabledMcpjsonServers whitelist
  3. ~/.claude/plugins/cache/**/.mcp.json -- plugin-bundled MCP definitions

Reports three drift classes:
  - Orphan whitelist: enabledMcpjsonServers references no plugin .mcp.json
  - Conflict state: same MCP in both enabledMcpjsonServers and disabledMcpServers
  - Bundled but inactive: plugin defines an MCP nobody whitelisted

Why: deferred tools list shown to the LLM at session start != MCPs actually
loaded. Plugin updates and stale user whitelists drift apart silently.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_json(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError, OSError):
        return None


def _claude_home() -> Path:
    return Path.home() / ".claude"


def discover_global_mcp(claude_json: dict | None) -> dict[str, dict]:
    if not claude_json:
        return {}
    return claude_json.get("mcpServers") or {}


def discover_project_mcp(claude_json: dict | None) -> dict[str, dict]:
    if not claude_json:
        return {}
    projects = claude_json.get("projects") or {}
    result: dict[str, dict] = {}
    for proj, conf in projects.items():
        for name, defn in (conf.get("mcpServers") or {}).items():
            result[name] = {**defn, "_project": proj}
    return result


def discover_disabled(claude_json: dict | None) -> set[str]:
    if not claude_json:
        return set()
    disabled: set[str] = set()
    for proj_conf in (claude_json.get("projects") or {}).values():
        for name in proj_conf.get("disabledMcpServers") or []:
            disabled.add(name)
    return disabled


def discover_whitelist(settings_files: list[Path]) -> set[str]:
    whitelist: set[str] = set()
    for f in settings_files:
        data = _load_json(f)
        if not data:
            continue
        for name in data.get("enabledMcpjsonServers") or []:
            whitelist.add(name)
    return whitelist


def discover_plugin_mcps(plugin_root: Path) -> dict[str, list[Path]]:
    """Return {mcp_name: [path, ...]} mapping each MCP to plugins that define it."""
    found: dict[str, list[Path]] = {}
    if not plugin_root.exists():
        return found
    for mcp_json in plugin_root.rglob(".mcp.json"):
        data = _load_json(mcp_json)
        if not data:
            continue
        for name in (data.get("mcpServers") or {}):
            found.setdefault(name, []).append(mcp_json)
    return found


def audit(home: Path | None = None) -> dict:
    """Run the audit and return a structured report."""
    home = home or _claude_home()
    claude_json = _load_json(Path.home() / ".claude.json")
    settings_files = [home / "settings.json", home / "settings.local.json"]
    plugin_root = home / "plugins" / "cache"

    global_mcp = discover_global_mcp(claude_json)
    project_mcp = discover_project_mcp(claude_json)
    disabled = discover_disabled(claude_json)
    whitelist = discover_whitelist(settings_files)
    plugin_mcps = discover_plugin_mcps(plugin_root)
    bundled = set(plugin_mcps)

    return {
        "summary": {
            "global_mcp": sorted(global_mcp),
            "project_mcp": sorted(project_mcp),
            "disabled": sorted(disabled),
            "whitelist": sorted(whitelist),
            "bundled_in_plugins": sorted(bundled),
        },
        "drift": {
            "orphan_whitelist": sorted(whitelist - bundled),
            "conflict_state": sorted(whitelist & disabled),
            "bundled_inactive": sorted(bundled - whitelist - set(global_mcp) - set(project_mcp)),
        },
        "plugin_origins": {
            name: [str(p) for p in paths] for name, paths in plugin_mcps.items()
        },
    }


def _print_human(report: dict, home: Path) -> bool:
    """Print human-readable report. Return True if drift was found."""
    s = report["summary"]
    d = report["drift"]

    print("=== cli2skill doctor -- MCP routing audit ===")
    print(f"Claude home: {home}")
    print()
    print(f"## Active MCPs")
    print(f"  Global mcpServers ({len(s['global_mcp'])}): {', '.join(s['global_mcp']) or '(none)'}")
    print(f"  Project mcpServers ({len(s['project_mcp'])}): {', '.join(s['project_mcp']) or '(none)'}")
    active_plugins = sorted(set(s['whitelist']) & set(s['bundled_in_plugins']))
    print(f"  Whitelisted plugin MCPs ({len(active_plugins)}): {', '.join(active_plugins) or '(none)'}")
    print()

    has_drift = bool(d["orphan_whitelist"] or d["conflict_state"] or d["bundled_inactive"])

    if not has_drift:
        print("OK: no drift detected. Routing chain is clean.")
        return False

    print("## Drift detected")
    if d["orphan_whitelist"]:
        print()
        print("[WARN] Orphan whitelist entries (enabledMcpjsonServers references no plugin):")
        for name in d["orphan_whitelist"]:
            print(f"  - {name}")
        print(f"  Fix: remove from enabledMcpjsonServers in ~/.claude/settings.local.json")

    if d["conflict_state"]:
        print()
        print("[FAIL] Conflict state (MCP in both enabled and disabled lists):")
        for name in d["conflict_state"]:
            print(f"  - {name}")
        print(f"  Fix: pick one. Remove from enabledMcpjsonServers OR from disabledMcpServers.")

    if d["bundled_inactive"]:
        print()
        print(f"[INFO] Plugin-bundled but not whitelisted ({len(d['bundled_inactive'])}):")
        for name in d["bundled_inactive"]:
            paths = report["plugin_origins"].get(name, [])
            origin = Path(paths[0]).name if paths else "?"
            print(f"  - {name} (defined in {origin})")
        print(f"  Note: these appear in deferred tools list but are NOT loaded.")
        print(f"        Add to enabledMcpjsonServers to activate, or ignore.")

    print()
    print("Tip: stateless MCPs (simple HTTP wrappers) are good candidates for")
    print("     conversion via `cli2skill mcp <command>` -- replaces the persistent")
    print("     process with an on-demand skill.")
    return True


def cmd_doctor(args: argparse.Namespace) -> None:
    home = _claude_home()
    report = audit(home)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(1 if any(report["drift"].values()) else 0)

    has_drift = _print_human(report, home)
    sys.exit(1 if has_drift else 0)
