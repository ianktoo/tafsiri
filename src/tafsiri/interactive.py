"""Interactive controller — the setup wizard and guided run.

This is a *controller*: it gathers input via the `ui` view and drives the
existing CLI/core. It adds no business logic of its own — translation,
evaluation, scoring, and persistence all stay in the core, untouched. Remove
this module and the flag-driven CLI still works exactly the same.
"""

from __future__ import annotations

import glob
import os
import subprocess
from pathlib import Path

from tafsiri import ui
from tafsiri.config import DEFAULT_TARGET_LANGUAGES, Settings
from tafsiri.providers import DarajaTranslator


# --- helpers -----------------------------------------------------------
def discover_samples(root: str = "samples") -> list[tuple[str, str]]:
    """(domain, path) for every bundled sample dataset."""
    out = []
    for path in sorted(glob.glob(f"{root}/*/*.jsonl")):
        out.append((Path(path).parent.name, path))
    return out


def detect_ollama_models() -> list[str]:
    try:
        res = subprocess.run(["ollama", "list"], capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    if res.returncode != 0:
        return []
    models = []
    for line in res.stdout.splitlines()[1:]:      # skip header
        name = line.split()[0] if line.split() else ""
        if name:
            models.append(name)
    return models


def write_env_key(env_path: Path, key: str,
                  example: Path = Path(".env.example")) -> None:
    """Set DARAJA_API_KEY in .env without disturbing other lines. Creates the
    file (from the example if present). Best-effort 0600 perms."""
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    elif example.exists():
        lines = example.read_text(encoding="utf-8").splitlines()

    found = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith("DARAJA_API_KEY="):
            lines[i] = f"DARAJA_API_KEY={key}"
            found = True
            break
    if not found:
        lines.append(f"DARAJA_API_KEY={key}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)   # no-op-ish on Windows, harmless
    except OSError:
        pass


def _test_key(key: str) -> tuple[bool, str]:
    settings = Settings.from_env()
    t = DarajaTranslator(key, base_url=settings.base_url, max_retries=0)
    r = t.translate("Hello", "English", "Swahili")
    return r.ok, (r.error or "")


# --- setup wizard ------------------------------------------------------
def run_setup(env_path: Path = Path(".env")) -> int:
    ui.banner()
    if not ui.is_interactive():
        ui.error("Setup needs an interactive terminal. "
                 "Set DARAJA_API_KEY in .env manually (see .env.example).")
        return 2

    ui.rule("Setup")
    existing = Settings.from_env().api_key
    if existing:
        ui.info(f"A key is already configured ({ui.mask_key(existing)}).")
        if not ui.confirm("Replace it?", default=False):
            ui.success("Keeping existing key.")
            return 0

    key = ui.ask("Daraja API key", password=True).strip()
    if not key:
        ui.error("No key entered.")
        return 2

    write_env_key(env_path, key)
    ui.success(f"Saved to {env_path} (gitignored) as {ui.mask_key(key)}")

    if ui.confirm("Test the key with one live call?", default=True):
        os.environ["DARAJA_API_KEY"] = key   # so the test picks it up now
        with ui.status("testing key…"):
            ok, err = _test_key(key)
        if ok:
            ui.success("Key works.")
        else:
            ui.error(f"Key test failed: {err}")

    models = detect_ollama_models()
    if models:
        ui.info(f"Local Ollama detected ({', '.join(models)}). "
                f"Use one as a free judge: --judge ollama:{models[0]}")
    ui.success("Setup complete.")
    return 0


# --- guided run wizard -------------------------------------------------
def run_wizard() -> int:
    ui.banner()
    if not ui.is_interactive():
        ui.error("No command given and not an interactive terminal. "
                 "Run `tafsiri run --help` for flags.")
        return 2

    # ensure a key exists
    if not Settings.from_env().api_key:
        ui.warn("No Daraja API key configured.")
        if ui.confirm("Run setup now?", default=True):
            rc = run_setup()
            if rc != 0:
                return rc
        else:
            return 2

    ui.rule("Configure run")
    models = detect_ollama_models()

    # engine
    engine_opts = ["daraja"] + [f"llm:ollama:{m}" for m in models] + ["custom…"]
    engine = ui.select("Translation engine", engine_opts, 0)
    if engine == "custom…":
        engine = ui.ask("engine spec (e.g. llm:openai:gpt-4o-mini)", default="daraja")

    # dataset
    samples = discover_samples()
    ds_opts = [f"{dom}  ({path})" for dom, path in samples] + ["custom path…"]
    ds_choice = ui.select("Dataset", ds_opts, 0)
    if ds_choice == "custom path…":
        source = ui.ask("path to JSONL/CSV")
    else:
        source = samples[ds_opts.index(ds_choice)][1]

    # languages
    langs = ui.multiselect("Target languages",
                           DEFAULT_TARGET_LANGUAGES + ["Hausa", "Zulu", "Igbo"],
                           DEFAULT_TARGET_LANGUAGES[:2])

    # judge (optional)
    judge = None
    if ui.confirm("Add an LLM-as-judge?", default=bool(models)):
        judge_opts = ([f"ollama:{m}" for m in models] + ["custom…"]) or ["custom…"]
        jc = ui.select("Judge model", judge_opts, 0)
        judge = ui.ask("judge spec", default="ollama:llama3.1") if jc == "custom…" else jc

    limit_raw = ui.ask("Limit to first N rows (blank = all)", default="")
    limit = int(limit_raw) if limit_raw.strip().isdigit() else 0

    ui.rule("Summary")
    ui.info(f"engine={engine}  source={source}")
    ui.info(f"languages={', '.join(langs)}  judge={judge or 'none'}  "
            f"limit={limit or 'all'}")
    if not ui.confirm("Run now?", default=True):
        ui.warn("Cancelled.")
        return 1

    # Drive the existing core run with the chosen config (lazy import avoids
    # a circular dependency; no core logic is duplicated here).
    from tafsiri.cli import build_parser
    args = build_parser().parse_args(["run"])
    args.engine, args.source = engine, source
    args.langs = ",".join(langs)
    args.judge, args.limit = judge, limit
    args.progress = True
    return args.func(args)
