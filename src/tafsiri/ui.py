"""Presentation layer — colors, tables, panels, and prompts.

This is a *view*: it renders plain data (rows/dicts the core already produces)
and collects user input. It depends on the core only for reading data shapes;
the core never imports this module. Swap or add another view (web, TUI) without
touching the pipeline.

Built on `rich`. Degrades gracefully: when output isn't a terminal, rich drops
colors automatically, and interactive prompts are gated behind `is_interactive()`
so nothing blocks in CI / pipes.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

console = Console()

RATING_STYLE = {"good": "bold green", "marginal": "yellow",
                "risky": "bold red", "no_score": "dim"}


def is_interactive() -> bool:
    """True only when we can safely prompt (a real terminal both ways)."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def mask_key(key: str | None) -> str:
    if not key:
        return "(none)"
    key = key.strip()
    return key if len(key) <= 10 else f"{key[:6]}…{key[-4:]}"


# --- messages ----------------------------------------------------------
def banner() -> None:
    console.print(Panel.fit(
        Text.assemble(("tafsiri", "bold cyan"),
                      ("  ·  African-language translation + evals", "dim")),
        border_style="cyan"))


def rule(title: str) -> None:
    console.rule(f"[bold]{title}", style="cyan")


def info(msg: str) -> None:
    console.print(f"[cyan]›[/] {msg}")


def success(msg: str) -> None:
    console.print(f"[bold green]✓[/] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]![/] {msg}")


def error(msg: str) -> None:
    console.print(f"[bold red]✗[/] {msg}")


@contextmanager
def status(msg: str):
    with console.status(f"[cyan]{msg}", spinner="dots"):
        yield


# --- prompts (only call when is_interactive()) -------------------------
def ask(label: str, default: str | None = None, password: bool = False,
        choices: list[str] | None = None) -> str:
    return Prompt.ask(label, default=default, password=password, choices=choices,
                      console=console)


def confirm(label: str, default: bool = True) -> bool:
    return Confirm.ask(label, default=default, console=console)


def select(label: str, options: list[str], default_index: int = 0) -> str:
    console.print(f"[bold]{label}[/]")
    for i, opt in enumerate(options, 1):
        marker = "[cyan]›[/]" if (i - 1) == default_index else " "
        console.print(f"  {marker} [bold]{i}[/]. {opt}")
    choice = Prompt.ask("  select", default=str(default_index + 1),
                        choices=[str(i) for i in range(1, len(options) + 1)],
                        console=console)
    return options[int(choice) - 1]


def multiselect(label: str, options: list[str],
                default_selected: list[str] | None = None) -> list[str]:
    default_selected = default_selected or []
    console.print(f"[bold]{label}[/] [dim](comma-separated numbers)[/]")
    for i, opt in enumerate(options, 1):
        on = "◉" if opt in default_selected else "◯"
        console.print(f"  {on} [bold]{i}[/]. {opt}")
    default_idx = ",".join(str(options.index(s) + 1) for s in default_selected
                           if s in options) or "1"
    raw = Prompt.ask("  select", default=default_idx, console=console)
    picked = []
    for tok in raw.replace(" ", "").split(","):
        if tok.isdigit() and 1 <= int(tok) <= len(options):
            picked.append(options[int(tok) - 1])
    return picked or default_selected


# --- renderers (consume plain data the core produced) ------------------
def render_results(rows: list[dict]) -> None:
    table = Table(show_lines=False, header_style="bold")
    table.add_column("source"); table.add_column("lang")
    table.add_column("score", justify="right"); table.add_column("rating")
    table.add_column("translation", overflow="ellipsis", max_width=46)
    for r in rows:
        score = ("" if r["aggregate_score"] is None
                 else f"{r['aggregate_score']:.3f}")
        style = RATING_STYLE.get(r["rating"], "")
        text = r["translation"] if r["ok"] else f"ERR: {r['error']}"
        table.add_row(str(r["source_id"]), str(r["tgt_lang"]), score,
                      Text(r["rating"], style=style), text)
    console.print(table)


def render_report(report: dict, run_id: str | None = None) -> None:
    c = report.get("rating_counts", {})
    head = Text.assemble(
        ("scored/ok/total ", "dim"), (f"{report.get('ok')}/{report.get('total')}\n"),
        ("avg score ", "dim"), (f"{report.get('avg_score')}   "),
        ("lowest ", "dim"), (f"{report.get('lowest_score')}\n"),
        ("good ", "dim"), (f"{c.get('good',0)}", "green"), ("  marginal ", "dim"),
        (f"{c.get('marginal',0)}", "yellow"), ("  risky ", "dim"),
        (f"{c.get('risky',0)}", "red"))
    console.print(Panel(head, title="eval report", border_style="cyan", expand=False))

    def _mini(title, mapping, keyname):
        if not mapping:
            return
        t = Table(title=title, title_style="bold", header_style="dim")
        t.add_column(keyname); t.add_column("n", justify="right")
        t.add_column("avg", justify="right")
        for k, v in mapping.items():
            t.add_row(str(k), str(v["count"]), str(v["avg_score"]))
        console.print(t)

    _mini("by signal", report.get("by_signal", {}), "signal")
    _mini("by language", report.get("by_language", {}), "language")
    _mini("by speaker", report.get("by_speaker", {}), "speaker")

    verdict = report.get("verdict", "")
    style = ("green" if verdict.startswith("GOOD")
             else "yellow" if verdict.startswith("CONDITIONAL") else "red")
    console.print(Panel(Text(verdict, style=f"bold {style}"), border_style=style))


def render_stopped(reason: str, resume_cmd: str) -> None:
    body = Text.assemble(
        (reason + "\n\n", ""),
        ("Partial results are saved. Continue where it left off:\n", "dim"),
        (f"  {resume_cmd}\n", "bold cyan"),
        ("Or: retry later · raise --delay · --no-backtranslation · new key", "dim"))
    console.print(Panel(body, title="stopped early (likely rate limiting)",
                        border_style="red"))
