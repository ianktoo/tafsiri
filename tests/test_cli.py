"""End-to-end CLI tests. Network-free: build_translator is monkeypatched to a
fake, so `run` exercises the full command path without hitting any provider."""

import json
from pathlib import Path

import pytest

from tafsiri import cli, config

from conftest import FakeTranslator


def _write_source(tmp_path, rows):
    p = tmp_path / "src.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                 encoding="utf-8")
    return p


@pytest.fixture
def fake_engine(monkeypatch):
    """Replace the real engine with a deterministic fake (no network)."""
    monkeypatch.setattr(cli, "build_translator",
                        lambda *a, **k: FakeTranslator(confidence=0.9))


def test_parser_no_command_has_no_func():
    args = cli.build_parser().parse_args([])
    assert getattr(args, "func", None) is None


def test_run_writes_all_outputs_and_persists(tmp_path, fake_engine):
    src = _write_source(tmp_path, [
        {"id": "a", "text": "Hello", "src_lang": "English"},
        {"id": "b", "text": "Please send help", "src_lang": "English"},
    ])
    db = tmp_path / "t.db"
    out = tmp_path / "out"
    rc = cli.main(["run", "--source", str(src), "--langs", "Swahili",
                   "--no-backtranslation", "--db", str(db), "--out-dir", str(out),
                   "--run-id", "r1"])
    assert rc == 0
    for name in ("r1.chat.jsonl", "r1.pairs.jsonl", "r1.csv",
                 "r1.report.json", "r1.report.md"):
        assert (out / name).exists(), name
    assert db.exists()
    report = json.loads((out / "r1.report.json").read_text(encoding="utf-8"))
    assert report["total"] == 2 and report["ok"] == 2


def test_run_handles_unicode_source_and_output(tmp_path, monkeypatch):
    # translator echoes unicode back; files must round-trip as UTF-8
    monkeypatch.setattr(cli, "build_translator",
                        lambda *a, **k: FakeTranslator(
                            mapping={("Ìkún omi", "Swahili"): "Mafuriko ń"}))
    src = _write_source(tmp_path, [{"id": "u", "text": "Ìkún omi"}])
    out = tmp_path / "out"
    rc = cli.main(["run", "--source", str(src), "--langs", "Swahili",
                   "--no-backtranslation", "--db", str(tmp_path / "t.db"),
                   "--out-dir", str(out), "--run-id", "uni"])
    assert rc == 0
    csv_text = (out / "uni.csv").read_text(encoding="utf-8")
    assert "Mafuriko ń" in csv_text and "Ìkún omi" in csv_text


def test_run_concurrency_path(tmp_path, fake_engine):
    src = _write_source(tmp_path, [{"id": str(i), "text": f"t{i}"} for i in range(6)])
    out = tmp_path / "out"
    rc = cli.main(["run", "--source", str(src), "--langs", "Swahili,Yoruba",
                   "--no-backtranslation", "--concurrency", "4",
                   "--db", str(tmp_path / "t.db"), "--out-dir", str(out),
                   "--run-id", "conc"])
    assert rc == 0
    rows = (out / "conc.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1 + 12          # header + 6 sources x 2 langs


def test_run_missing_key_exits_2(tmp_path, monkeypatch):
    # no fake engine; force no key so the daraja engine init fails cleanly
    monkeypatch.delenv("DARAJA_API_KEY", raising=False)
    monkeypatch.setattr(config.Settings, "from_env",
                        classmethod(lambda cls: config.Settings(api_key=None)))
    src = _write_source(tmp_path, [{"id": "a", "text": "hi"}])
    rc = cli.main(["run", "--engine", "daraja", "--source", str(src),
                   "--db", str(tmp_path / "t.db"), "--out-dir", str(tmp_path / "o")])
    assert rc == 2


def test_report_formats(tmp_path, fake_engine, capsys):
    src = _write_source(tmp_path, [{"id": "a", "text": "hi"}])
    db = tmp_path / "t.db"
    cli.main(["run", "--source", str(src), "--langs", "Swahili",
              "--no-backtranslation", "--db", str(db),
              "--out-dir", str(tmp_path / "o"), "--run-id", "rep"])
    capsys.readouterr()

    assert cli.main(["report", "rep", "--db", str(db), "--format", "json"]) == 0
    out_json = capsys.readouterr().out
    assert json.loads(out_json)["total"] == 1

    md_path = tmp_path / "f.md"
    assert cli.main(["report", "rep", "--db", str(db), "--format", "md",
                     "--out", str(md_path)]) == 0
    assert "# Findings" in md_path.read_text(encoding="utf-8")

    assert cli.main(["report", "missing", "--db", str(db)]) == 1   # unknown run


def test_runs_lists_after_run(tmp_path, fake_engine, capsys):
    src = _write_source(tmp_path, [{"id": "a", "text": "hi"}])
    db = tmp_path / "t.db"
    cli.main(["run", "--source", str(src), "--langs", "Swahili",
              "--no-backtranslation", "--db", str(db),
              "--out-dir", str(tmp_path / "o"), "--run-id", "listme"])
    capsys.readouterr()
    cli.main(["runs", "--db", str(db)])
    assert "listme" in capsys.readouterr().out


def test_data_home_respects_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TAFSIRI_HOME", str(tmp_path / "store"))
    assert config.default_db_path() == str(tmp_path / "store" / "tafsiri.db")
    assert config.default_out_dir() == str(tmp_path / "store" / "out")


def test_data_home_defaults_under_user_home(monkeypatch):
    monkeypatch.delenv("TAFSIRI_HOME", raising=False)
    assert config.data_home() == Path.home() / ".tafsiri"
