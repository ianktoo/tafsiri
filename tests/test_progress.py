import io

from tafsiri.progress import Progress


class FakeTTY(io.StringIO):
    """StringIO that claims to be a terminal so Progress renders."""

    def isatty(self) -> bool:
        return True


def test_counts_track_regardless_of_tty():
    # plain StringIO is not a tty -> disabled, but counters still move
    stream = io.StringIO()
    p = Progress(total=3, enabled=True, stream=stream)
    assert p.enabled is False
    p.update("a", ok=True)
    p.update("b", ok=False)
    assert (p.done, p.ok, p.failed) == (2, 1, 1)
    assert stream.getvalue() == ""   # nothing drawn when not a tty


def test_disabled_by_flag_even_on_tty():
    p = Progress(total=3, enabled=False, stream=FakeTTY())
    assert p.enabled is False


def test_renders_on_tty_and_finish_clears():
    stream = FakeTTY()
    p = Progress(total=2, enabled=True, stream=stream)
    assert p.enabled is True
    p.update("flood → Swahili", ok=True)
    out = stream.getvalue()
    assert "1/2" in out
    assert "flood → Swahili" in out
    p.finish()
    # finish writes a carriage-return clear sequence
    assert stream.getvalue().endswith("\r")


def test_note_prints_above_bar(capsys):
    stream = FakeTTY()
    p = Progress(total=2, enabled=True, stream=stream)
    p.update("x", ok=False)
    p.note("cooling down 5s")
    captured = capsys.readouterr()
    assert "cooling down 5s" in captured.out


def test_zero_total_is_safe():
    p = Progress(total=0, enabled=True, stream=FakeTTY())
    assert p.enabled is False   # nothing to show
    p.finish()
