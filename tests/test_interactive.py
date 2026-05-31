from pathlib import Path

from tafsiri import interactive


def test_discover_samples(tmp_path):
    (tmp_path / "tech").mkdir()
    (tmp_path / "finance").mkdir()
    (tmp_path / "tech" / "a.jsonl").write_text('{"text":"x"}\n', encoding="utf-8")
    (tmp_path / "finance" / "b.jsonl").write_text('{"text":"y"}\n', encoding="utf-8")
    found = interactive.discover_samples(str(tmp_path))
    domains = sorted(d for d, _ in found)
    assert domains == ["finance", "tech"]


def test_write_env_key_creates_file(tmp_path):
    env = tmp_path / ".env"
    interactive.write_env_key(env, "dk_new", example=tmp_path / "missing.example")
    assert env.read_text(encoding="utf-8").strip() == "DARAJA_API_KEY=dk_new"


def test_write_env_key_updates_existing_line_preserving_others(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nDARAJA_API_KEY=old\nOTHER=keep\n", encoding="utf-8")
    interactive.write_env_key(env, "dk_new")
    text = env.read_text(encoding="utf-8")
    assert "DARAJA_API_KEY=dk_new" in text
    assert "DARAJA_API_KEY=old" not in text
    assert "# comment" in text and "OTHER=keep" in text


def test_write_env_key_seeds_from_example(tmp_path):
    example = tmp_path / ".env.example"
    example.write_text("DARAJA_API_KEY=<your-daraja-api-key>\n# OPENAI_API_KEY=x\n",
                       encoding="utf-8")
    env = tmp_path / ".env"
    interactive.write_env_key(env, "dk_real", example=example)
    text = env.read_text(encoding="utf-8")
    assert "DARAJA_API_KEY=dk_real" in text
    assert "OPENAI_API_KEY" in text          # other example lines carried over
