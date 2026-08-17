"""Shared input sanitizer (security §3).

Strips ASCII control characters (except common whitespace) that could corrupt
logs, PDFs, or downstream parsing, and trims surrounding whitespace.
"""

# Control chars \x00-\x08, \x0b, \x0c, \x0e-\x1f, and \x7f. Keep \t \n \r.
_CONTROL_CHARS = {c for c in range(0x00, 0x20)} - {0x09, 0x0A, 0x0D}
_CONTROL_CHARS.add(0x7F)
_TRANSLATION = {c: None for c in _CONTROL_CHARS}


def sanitize_text(value: str) -> str:
    if not isinstance(value, str):
        return value
    return value.translate(_TRANSLATION).strip()
