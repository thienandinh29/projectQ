import pytest

from app.sources.licence import LicenceError, is_non_commercial, licence_from_url


@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("http://creativecommons.org/licenses/by/4.0/", "CC BY 4.0"),
        ("https://creativecommons.org/licenses/by-sa/3.0/", "CC BY-SA 3.0"),
        ("http://creativecommons.org/licenses/by-nc-sa/4.0/", "CC BY-NC-SA 4.0"),
        ("HTTPS://CreativeCommons.org/licenses/by-nc/2.5/", "CC BY-NC 2.5"),
        ("https://creativecommons.org/publicdomain/zero/1.0/", "CC0 1.0"),
    ],
)
def test_known_licences_map_to_names(url: str, name: str) -> None:
    assert licence_from_url(url) == name


@pytest.mark.parametrize(
    "url",
    [
        "http://creativecommons.org/licenses/by-nd/4.0/",
        "http://creativecommons.org/licenses/by-nc-nd/4.0/",
    ],
)
def test_no_derivatives_is_refused(url: str) -> None:
    with pytest.raises(LicenceError, match="NoDerivatives"):
        licence_from_url(url)


@pytest.mark.parametrize("url", ["", "https://example.org/terms", "http://creativecommons.org/"])
def test_unknown_licence_is_refused_not_guessed(url: str) -> None:
    with pytest.raises(LicenceError, match="unknown"):
        licence_from_url(url)


def test_non_commercial_flag() -> None:
    assert is_non_commercial("CC BY-NC-SA 4.0")
    assert not is_non_commercial("CC BY-SA 4.0")
