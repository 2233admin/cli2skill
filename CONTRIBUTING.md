# Contributing to cli2skill

## Quick Wins

- **Test with your CLI tools** — run `cli2skill generate <your-tool>` and report how it handles your help format
- **Report unsupported help formats** — if parsing fails for a specific CLI framework, file an issue with the `--help` output
- **Add examples** — generated skills for popular CLIs (aws, docker, kubectl, terraform...)

## Development

```bash
git clone https://github.com/2233admin/cli2skill.git
cd cli2skill
pip install -e .
cli2skill preview gh
```

Python 3.10+. Zero external dependencies.

## Architecture

```
cli2skill/
├── main.py        ← CLI entry point (Typer-style)
├── parser.py      ← --help output parser (regex-based, multi-framework)
├── generator.py   ← SKILL.md markdown generator
└── mcp2skill.py   ← MCP server → CLI skill converter
```

## Adding Support for a New CLI Framework

1. Add a detection pattern in `parser.py`
2. Add a test case in `examples/`
3. Document the framework in the Supported Formats table

## Ideas

- [ ] Auto-detect framework from help output format
- [ ] `cli2skill batch` — convert all CLIs in PATH
- [ ] `cli2skill mcp-audit` — scan settings.json, show which MCPs can be replaced
- [ ] Web UI for previewing generated skills
- [ ] Integration with `skills-cli` install flow
