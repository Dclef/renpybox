init python:
    import io
    import json
    import os

    _renpybox_runtime_extract_output = "extraction_hooked.json"
    _renpybox_translator = renpy.game.script.translator
    _renpybox_default_translates = getattr(_renpybox_translator, "default_translates", {}) or {}
    _renpybox_additional_strings = getattr(_renpybox_translator, "additional_strings", {}) or {}
    _renpybox_tl_name = os.environ.get("RENPYBOX_TL_NAME", "")
    _renpybox_payload = {
        "dialogues": {},
        "strings": {},
    }

    try:
        _renpybox_text_type = unicode
    except NameError:
        _renpybox_text_type = str

    def _renpybox_to_text(value):
        if value is None:
            return None
        if isinstance(value, _renpybox_text_type):
            return value
        try:
            return _renpybox_text_type(value)
        except Exception:
            return str(value)

    def _renpybox_find_say(node):
        if hasattr(node, "block"):
            for stmt in node.block:
                if hasattr(stmt, "what"):
                    return stmt
            return None
        if hasattr(node, "what"):
            return node
        return None

    def _renpybox_get_string_bucket():
        _strings = getattr(_renpybox_translator, "strings", {}) or {}
        if hasattr(_strings, "get"):
            return _strings.get(_renpybox_tl_name)
        return None

    def _renpybox_append_string(filename, original, translated):
        original = _renpybox_to_text(original)
        if not original:
            return

        translated = _renpybox_to_text(translated)
        if translated is None:
            translated = original

        if not filename:
            filename = "strings.rpy"

        _renpybox_payload["strings"].setdefault(filename, []).append(
            [original, translated]
        )

    _renpybox_string_bucket = _renpybox_get_string_bucket()
    _renpybox_string_translations = getattr(_renpybox_string_bucket, "translations", {}) or {}

    for _renpybox_identifier, _renpybox_value in _renpybox_default_translates.items():
        _renpybox_say = _renpybox_find_say(_renpybox_value)
        if _renpybox_say is None:
            continue

        _renpybox_what = getattr(_renpybox_say, "what", None)
        if _renpybox_what is None:
            continue

        _renpybox_filename = _renpybox_to_text(getattr(_renpybox_value, "filename", None))
        if not _renpybox_filename:
            continue

        _renpybox_payload["dialogues"].setdefault(_renpybox_filename, []).append(
            [
                _renpybox_to_text(_renpybox_identifier),
                _renpybox_to_text(getattr(_renpybox_say, "who", None)),
                _renpybox_to_text(_renpybox_what),
                getattr(_renpybox_value, "linenumber", 0),
            ]
        )

    for _renpybox_filename, _renpybox_strings in _renpybox_additional_strings.items():
        _renpybox_filename = _renpybox_to_text(_renpybox_filename)
        if not isinstance(_renpybox_strings, (list, tuple)):
            continue

        _renpybox_seen = set()
        for _renpybox_original in _renpybox_strings:
            _renpybox_original = _renpybox_to_text(_renpybox_original)
            if not _renpybox_original or _renpybox_original in _renpybox_seen:
                continue
            _renpybox_seen.add(_renpybox_original)

            _renpybox_append_string(
                _renpybox_filename,
                _renpybox_original,
                _renpybox_string_translations.get(_renpybox_original, _renpybox_original),
            )

    _renpybox_unknown = getattr(_renpybox_string_bucket, "unknown", None)
    if isinstance(_renpybox_unknown, (list, tuple, set)):
        for _renpybox_original in _renpybox_unknown:
            _renpybox_append_string(
                "strings.rpy",
                _renpybox_original,
                _renpybox_string_translations.get(_renpybox_original, _renpybox_original),
            )

    with io.open(_renpybox_runtime_extract_output, "w", encoding="utf-8") as _renpybox_out:
        _renpybox_json = json.dumps(_renpybox_payload, ensure_ascii=False)
        if not isinstance(_renpybox_json, _renpybox_text_type):
            _renpybox_json = _renpybox_json.decode("utf-8")
        _renpybox_out.write(_renpybox_json)

    renpy.quit()
