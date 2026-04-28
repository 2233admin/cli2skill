"""cli2skill doctor -- audit Claude Code MCP routing chain.

Five sources of MCP definitions:

  G   ~/.claude.json mcpServers (global)            -> mcp__<name>__
  P   ~/.claude.json projects[*].mcpServers          -> mcp__<name>__ (per-cwd)
  Uh  ~/.mcp.json                                    -> mcp__<name>__ (gated by W)
  Uc  ~/.claude/.mcp.json                            -> mcp__<name>__ (gated by W)
  PL  ~/.claude/plugins/cache/**/.mcp.json           -> mcp__plugin_<plugin>_<name>__

Two gates:

  W   ~/.claude/settings.{json,local.json} enabledMcpjsonServers (whitelist Uh+Uc)
  D   ~/.claude.json projects[*].disabledMcpServers (blacklist)

Drift classes:

  - Orphan whitelist: W entry not defined in Uh or Uc (whitelist references nothing)
  - Conflict state:   MCP in both W and D (resolution ambiguous)
  - Duplicate names:  same MCP name in 2+ user-level sources (routing ambiguity)

Plugin MCPs are reported informationally, not as drift. Plugin .mcp.json files
auto-load when the plugin is installed and prefix tools as `plugin_<plugin>_`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Source labels
G_GLOBAL = "global"
G_PROJECT = "project"
G_USER_HOME = "user_home"
G_USER_CLAUDE = "user_claude"
G_PLUGIN = "plugin"

USER_LEVEL_SOURCES = (G_GLOBAL, G_PROJECT, G_USER_HOME, G_USER_CLAUDE)
WHITELIST_GATED_SOURCES = (G_USER_HOME, G_USER_CLAUDE)


def _load_json(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError, OSError):
        return None


def _claude_home() -> Path:
    return Path.home() / ".claude"


def discover_user_level(claude_home: Path) -> dict[str, list[tuple[str, dict]]]:
    """Return {name: [(source_label, defn), ...]} across G, P, Uh, Uc."""
    found: dict[str, list[tuple[str, dict]]] = {}
    home = Path.home()

    # G + P from ~/.claude.json
    claude_json = _load_json(home / ".claude.json")
    if claude_json:
        for name, defn in (claude_json.get("mcpServers") or {}).items():
            found.setdefault(name, []).append((G_GLOBAL, defn))
        for proj, conf in (claude_json.get("projects") or {}).items():
            for name, defn in (conf.get("mcpServers") or {}).items():
                found.setdefault(name, []).append((G_PROJECT, {**defn, "_project": proj}))

    # Uh from ~/.mcp.json
    user_home_mcp = _load_json(home / ".mcp.json")
    if user_home_mcp:
        for name, defn in (user_home_mcp.get("mcpServers") or {}).items():
            found.setdefault(name, []).append((G_USER_HOME, defn))

    # Uc from ~/.claude/.mcp.json
    user_claude_mcp = _load_json(claude_home / ".mcp.json")
    if user_claude_mcp:
        for name, defn in (user_claude_mcp.get("mcpServers") or {}).items():
            found.setdefault(name, []).append((G_USER_CLAUDE, defn))

    return found


def discover_plugin_level(claude_home: Path) -> dict[str, list[tuple[str, Path]]]:
    """Return {name: [(plugin_name, path), ...]} from plugin .mcp.json files."""
    found: dict[str, list[tuple[str, Path]]] = {}
    plugin_root = claude_home / "plugins" / "cache"
    if not plugin_root.exists():
        return found
    for mcp_json in plugin_root.rglob(".mcp.json"):
        data = _load_json(mcp_json)
        if not data:
            continue
        rel = mcp_json.relative_to(plugin_root)
        plugin_name = rel.parts[0] if rel.parts else "?"
        for name in (data.get("mcpServers") or {}):
            found.setdefault(name, []).append((plugin_name, mcp_json))
    return found


def discover_disabled(claude_home: Path) -> set[str]:
    home = Path.home()
    claude_json = _load_json(home / ".claude.json")
    if not claude_json:
        return set()
    disabled: set[str] = set()
    for proj_conf in (claude_json.get("projects") or {}).values():
        for name in (proj_conf.get("disabledMcpServers") or []):
            disabled.add(name)
    return disabled


def discover_whitelist(claude_home: Path) -> set[str]:
    whitelist: set[str] = set()
    for fname in ("settings.json", "settings.local.json"):
        data = _load_json(claude_home / fname)
        if not data:
            continue
        for name in (data.get("enabledMcpjsonServers") or []):
            whitelist.add(name)
    return whitelist


def audit(claude_home: Path | None = None) -> dict:
    home = claude_home or _claude_home()
    user_level = discover_user_level(home)
    plugin_level = discover_plugin_level(home)
    disabled = discover_disabled(home)
    whitelist = discover_whitelist(home)

    # Names defined at user level (any of G/P/Uh/Uc)
    user_level_names = set(user_level)
    # Names gated by whitelist (Uh + Uc only)
    whitelist_gated_names = {
        n for n, srcs in user_level.items()
        if any(s in WHITELIST_GATED_SOURCES for s, _ in srcs)
    }

    # Drift: orphan whitelist = W entry not in any U source
    orphan_whitelist = sorted(whitelist - whitelist_gated_names)

    # Drift: conflict state = same name in W and D
    conflict_state = sorted(whitelist & disabled)

    # Drift: duplicate definitions across user-level sources
    duplicates = []
    for name, sources in user_level.items():
        labels = [s for s, _ in sources]
        if len(labels) >= 2:
            duplicates.append({"name": name, "sources": labels})

    # Group plugin-level MCPs by plugin name
    by_plugin: dict[str, list[str]] = {}
    for name, entries in plugin_level.items():
        for plugin_name, _ in entries:
            by_plugin.setdefault(plugin_name, []).append(name)
    plugin_groups = {p: sorted(set(names)) for p, names in by_plugin.items()}

    return {
        "summary": {
            "user_level": {
                src: sorted(n for n, srcs in user_level.items() if any(s == src for s, _ in srcs))
                for src in USER_LEVEL_SOURCES
            },
            "whitelist": sorted(whitelist),
            "disabled": sorted(disabled),
            "plugin_count": len(plugin_groups),
            "plugin_total_mcps": sum(len(v) for v in plugin_groups.values()),
        },
        "drift": {
            "orphan_whitelist": orphan_whitelist,
            "conflict_state": conflict_state,
            "duplicate_definitions": duplicates,
        },
        "plugin_namespace": plugin_groups,
    }


def _print_human(report: dict, home: Path) -> bool:
    s = report["summary"]
    d = report["drift"]
    ul = s["user_level"]

    print("=== cli2skill doctor -- MCP routing audit ===")
    print(f"Claude home: {home}")
    print()
    print("## User-level MCPs (loaded as mcp__<name>__)")
    print(f"  global  ~/.claude.json mcpServers ({len(ul[G_GLOBAL])}): {', '.join(ul[G_GLOBAL]) or '(none)'}")
    print(f"  project ~/.claude.json projects ({len(ul[G_PROJECT])}): {', '.join(ul[G_PROJECT]) or '(none)'}")
    print(f"  user    ~/.mcp.json ({len(ul[G_USER_HOME])}): {', '.join(ul[G_USER_HOME]) or '(none)'}")
    print(f"  claude  ~/.claude/.mcp.json ({len(ul[G_USER_CLAUDE])}): {', '.join(ul[G_USER_CLAUDE]) or '(none)'}")
    print()
    print(f"## Whitelist (enabledMcpjsonServers, {len(s['whitelist'])}): {', '.join(s['whitelist']) or '(none)'}")
    print(f"## Disabled (disabledMcpServers, {len(s['disabled'])}): {', '.join(s['disabled']) or '(none)'}")
    print()

    has_drift = bool(d["orphan_whitelist"] or d["conflict_state"] or d["duplicate_definitions"])

    if not has_drift:
        print("OK: no drift detected.")
    else:
        print("## Drift detected")
        if d["orphan_whitelist"]:
            print()
            print("[WARN] Orphan whitelist entries (W references no Uh or Uc definition):")
            for name in d["orphan_whitelist"]:
                print(f"  - {name}")
            print(f"  Fix: remove from enabledMcpjsonServers in ~/.claude/settings.local.json")
            print(f"       (these whitelist entries don't gate anything; whitelist only")
            print(f"        gates ~/.mcp.json and ~/.claude/.mcp.json definitions)")

        if d["conflict_state"]:
            print()
            print("[FAIL] Conflict state (MCP in both W and D, resolution ambiguous):")
            for name in d["conflict_state"]:
                print(f"  - {name}")
            print(f"  Fix: pick one. Remove from enabledMcpjsonServers OR from disabledMcpServers.")

        if d["duplicate_definitions"]:
            print()
            print("[FAIL] Duplicate definitions (same name in 2+ sources, routing ambiguous):")
            for dup in d["duplicate_definitions"]:
                print(f"  - {dup['name']}: defined in {', '.join(dup['sources'])}")
            print(f"  Fix: keep one definition, remove the others. Same MCP name with")
            print(f"       different commands across sources causes silent surprises.")

    if s["plugin_count"]:
        print()
        print(f"## Plugin namespace (informational, auto-loaded as mcp__plugin_<plugin>_<name>__)")
        print(f"  {s['plugin_count']} plugins bundling {s['plugin_total_mcps']} MCPs total")
        for plugin in sorted(report["plugin_namespace"]):
            mcps = report["plugin_namespace"][plugin]
            preview = ", ".join(mcps[:5]) + (f", +{len(mcps)-5} more" if len(mcps) > 5 else "")
            print(f"  - {plugin}: {len(mcps)} MCP{'s' if len(mcps)!=1 else ''} ({preview})")
        print(f"  Note: these are NOT drift. Plugin MCPs auto-load with their plugin.")

    print()
    print("Tip: stateless MCPs (HTTP wrappers) are good candidates for conversion via")
    print("     `cli2skill mcp <command>` -- replaces persistent process with skill.")
    return has_drift


def cmd_doctor(args: argparse.Namespace) -> None:
    home = _claude_home()
    report = audit(home)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        sys.exit(1 if any(report["drift"].values()) else 0)

    has_drift = _print_human(report, home)
    sys.exit(1 if has_drift else 0)
