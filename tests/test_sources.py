import pytest

from tafsiri.sources import load_csv, load_jsonl, load_source


def test_load_jsonl_maps_known_and_meta_fields(tmp_path):
    p = tmp_path / "src.jsonl"
    p.write_text(
        '{"id": "a1", "text": "hi", "src_lang": "English", "speaker": "x"}\n'
        '\n'  # blank line is skipped
        '{"id": "a2", "text": "bye", "category": "medical"}\n',
        encoding="utf-8",
    )
    recs = load_jsonl(p)
    assert len(recs) == 2
    assert recs[0].id == "a1"
    assert recs[0].text == "hi"
    assert recs[0].src_lang == "English"
    assert recs[0].meta == {"speaker": "x"}
    # default src_lang applied; unknown field lands in meta
    assert recs[1].src_lang == "English"
    assert recs[1].meta == {"category": "medical"}


def test_load_jsonl_generates_id_when_missing(tmp_path):
    p = tmp_path / "src.jsonl"
    p.write_text('{"text": "no id here"}\n', encoding="utf-8")
    recs = load_jsonl(p)
    assert recs[0].id == "row-0"


def test_load_jsonl_missing_text_raises(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"id": "x"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="missing text"):
        load_jsonl(p)


def test_load_csv_uses_alternate_text_keys(tmp_path):
    p = tmp_path / "src.csv"
    p.write_text("id,source_text,lang\nc1,hello,English\n", encoding="utf-8")
    recs = load_csv(p)
    assert recs[0].id == "c1"
    assert recs[0].text == "hello"
    assert recs[0].src_lang == "English"


def test_load_source_dispatches_by_extension(tmp_path):
    j = tmp_path / "a.jsonl"
    j.write_text('{"id":"1","text":"t"}\n', encoding="utf-8")
    assert load_source(j)[0].text == "t"
    with pytest.raises(ValueError, match="unsupported source format"):
        load_source(tmp_path / "a.txt")
