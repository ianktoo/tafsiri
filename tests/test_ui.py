from tafsiri import ui


def test_mask_key_short_and_long():
    assert ui.mask_key(None) == "(none)"
    assert ui.mask_key("") == "(none)"
    assert ui.mask_key("short") == "short"            # <=10 shown as-is
    assert ui.mask_key("dk_dev_2bee9843c37cf4e9") == "dk_dev…f4e9"


def test_is_interactive_returns_bool():
    assert isinstance(ui.is_interactive(), bool)


def test_render_functions_do_not_crash_on_empty():
    # rendering empty data should be safe (rich degrades to plain when not a tty)
    ui.render_results([])
    ui.render_report({"ok": 0, "total": 0, "rating_counts": {}, "verdict": ""})
