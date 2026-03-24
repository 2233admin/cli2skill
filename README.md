# cli2skill

**Turn any CLI into an Agent Skill — zero MCP overhead.**

MCP servers leak processes, eat memory, and add complexity. `cli2skill` generates [Agent Skills](https://agentskills.io) from any CLI's `--help` output. Your agent calls your tool via `Bash`, the tool runs and exits. No persistent processes, no JSON-RPC, no zombie cleanup.

Works with: **Claude Code** · **Codex CLI** · **Gemini CLI** · **Cursor** · **Copilot** — any platform supporting the Agent Skills spec (26+).

## Install

```bash
pip install cli2skill
# or run directly
python -m cli2skill.main generate <your-tool>
```

## Quick Start

```bash
# Generate a skill from any CLI
cli2skill generate gh --name github-cli -o ~/.claude/skills/

# Preview what cli2skill parses
cli2skill preview mytool

# Use a custom executable path
cli2skill generate "python my_script.py" --name my-tool --exe-path "python /full/path/my_script.py"

# Parse from a file instead of running --help
cli2skill generate mytool --help-file help_output.txt
```

## Example Output

```bash
cli2skill generate gh --name github-cli --no-subcommands
```

Generates:

```markdown
---
name: github-cli
description: Work seamlessly with GitHub from the command line.
user-invocable: false
allowed-tools: Bash(gh *)
---

# github-cli

## Commands

gh auth
gh browse
gh issue
gh pr
gh repo
...

## When to use
- Work seamlessly with GitHub from the command line.
- Available commands: `auth`, `browse`, `issue`, `pr`, `repo`
```

Drop this in `~/.claude/skills/` and your agent can use `gh` without an MCP server.

## Why Not MCP?

| | MCP Server | CLI + Skill |
|---|---|---|
| **Processes** | 3 per server (cmd→uv→python), persistent | 1 per call, exits immediately |
| **Memory** | Accumulates across sessions | Zero when idle |
| **Debugging** | JSON-RPC over stdio pipes | `stderr` |
| **Platforms** | Claude Code only | 26+ platforms via Agent Skills spec |
| **Token cost** | 150k per workflow | 2k per workflow ([Anthropic's own data](https://www.anthropic.com/engineering/code-execution-with-mcp)) |

MCP is still good for: persistent browser sessions, multi-client shared servers, streaming notifications, remote HTTP endpoints (Slack/GitHub/Notion).

For everything else: **CLI + Skill wins.**

## Supported Formats

| Framework | Language | Detection |
|---|---|---|
| argparse / Click / Typer | Python | `  command   description` format |
| Cobra | Go | `  command:  description` format |
| Commander.js | TypeScript | `  command   description` format |
| clap | Rust | `  command   description` format |
| Any CLI | Any | Generic `--help` parsing |

## Background

This tool was born from a real incident: 15 MCP servers accumulated 400+ zombie processes on a 32GB Windows machine, exhausting commit charge and killing all shell operations. Full story in [ARTICLE.md](./ARTICLE.md).

**Related:**
- [Agent Skills Specification](https://agentskills.io/specification) — Anthropic, 26+ platforms
- [CLI-Anything](https://github.com/HKUDS/CLI-Anything) — HKU, making software agent-native (22.3k stars)
- [anthropics/claude-code#38228](https://github.com/anthropics/claude-code/issues/38228) — MCP process leak bug report

## License

MIT
