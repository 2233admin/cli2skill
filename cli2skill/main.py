"""cli2skill — Turn any CLI into an Agent Skill."""
from __future__ import annotations
import argparse
import os
import sys
from .parser import run_help, parse_help_text, parse_subcommand_help
from .generator import generate_skill


def cmd_generate(args: argparse.Namespace) -> None:
    """Generate a SKILL.md for a CLI tool."""
    name = args.name or args.executable
    executable = args.executable

    # Get help text
    if args.help_file:
        with open(args.help_file, encoding="utf-8") as f:
            help_text = f.read()
    else:
        help_text = run_help(executable)

    # Parse
    meta = parse_help_text(name, help_text)

    # Enrich subcommands if requested
    if meta.commands and not args.no_subcommands and not args.help_file:
        meta = parse_subcommand_help(executable, meta)

    # Override executable path if specified
    exe = args.exe_path or executable

    # Generate
    skill_content = generate_skill(meta, executable=exe)

    # Output
    if args.output:
        out_dir = args.output
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{name}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(skill_content)
        print(f"Skill written to: {out_path}")
    else:
        print(skill_content)


def cmd_preview(args: argparse.Namespace) -> None:
    """Preview what --help gives us without generating."""
    help_text = run_help(args.executable)
    name = args.name or args.executable
    meta = parse_help_text(name, help_text)

    print(f"Name: {meta.name}")
    print(f"Description: {meta.description[:200]}")
    print(f"Commands: {len(meta.commands)}")
    for cmd in meta.commands:
        print(f"  - {cmd.name}: {cmd.description[:100]}")
    print(f"Global options: {len(meta.global_options)}")
    for opt in meta.global_options:
        print(f"  - {opt.flags}: {opt.description[:80]}")


def app() -> None:
    p = argparse.ArgumentParser(
        prog="cli2skill",
        description="Turn any CLI into an Agent Skill (SKILL.md)",
    )
    sub = p.add_subparsers(dest="cmd")

    # generate
    g = sub.add_parser("generate", aliases=["gen", "g"], help="Generate SKILL.md")
    g.add_argument("executable", help="CLI command to analyze")
    g.add_argument("--name", help="Skill name (default: executable name)")
    g.add_argument("--output", "-o", help="Output directory")
    g.add_argument("--exe-path", help="Full executable path for skill (e.g. 'python /path/to/tool.py')")
    g.add_argument("--help-file", help="Read --help text from file instead of running")
    g.add_argument("--no-subcommands", action="store_true", help="Skip subcommand help parsing")
    g.set_defaults(func=cmd_generate)

    # preview
    pv = sub.add_parser("preview", aliases=["p"], help="Preview parsed metadata")
    pv.add_argument("executable", help="CLI command to analyze")
    pv.add_argument("--name", help="Override name")
    pv.set_defaults(func=cmd_preview)

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    app()
