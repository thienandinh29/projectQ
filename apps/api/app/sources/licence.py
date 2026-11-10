"""Licence names from machine-readable licence URLs (Creative Commons and public domain).

A structured source states its licence as a URL in its metadata, so there is nothing to guess:
the URL either maps to a known open licence or the book is refused. NoDerivatives licences are
refused because NodeTrail derives questions and explanations from the text (`SPEC.md`).
"""

import re

_CC = re.compile(r"creativecommons\.org/licenses/(?P<code>[a-z-]+)/(?P<version>\d\.\d)")
_CODES = {"by": "BY", "by-sa": "BY-SA", "by-nc": "BY-NC", "by-nc-sa": "BY-NC-SA"}
_ND_CODES = {"by-nd", "by-nc-nd"}


class LicenceError(ValueError):
    """The licence is unknown or does not allow derived works."""


def licence_from_url(url: str) -> str:
    """`https://creativecommons.org/licenses/by-nc-sa/4.0/` -> `CC BY-NC-SA 4.0`."""
    normalized = url.strip().casefold()
    if "creativecommons.org/publicdomain/zero/1.0" in normalized:
        return "CC0 1.0"
    if "creativecommons.org/publicdomain/mark/1.0" in normalized:
        return "Public Domain Mark 1.0"
    found = _CC.search(normalized)
    if found is None:
        raise LicenceError(f"unknown licence URL: {url!r}")
    code, version = found["code"], found["version"]
    if code in _ND_CODES:
        raise LicenceError(f"NoDerivatives licence is not allowed: {url!r}")
    if code not in _CODES:
        raise LicenceError(f"unknown Creative Commons licence: {url!r}")
    return f"CC {_CODES[code]} {version}"


def is_non_commercial(licence: str) -> bool:
    """True for NonCommercial licences: fine for study, a commercial release needs a review."""
    return "-NC" in licence
