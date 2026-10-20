"""Python's requests to the server skip the slow IPv6 «localhost» on Windows."""

import pytest
from sergio_escritorio.voice import SergioClient, api_base


@pytest.mark.parametrize(
    "url, expected",
    [
        ("http://localhost:8000", "http://127.0.0.1:8000"),
        ("http://localhost:8000/", "http://127.0.0.1:8000"),
        ("https://localhost", "https://127.0.0.1"),
        ("http://localhostile:8000", "http://localhostile:8000"),
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
        ("http://sergio.lan:8000", "http://sergio.lan:8000"),
    ],
)
def test_api_base(url, expected):
    assert api_base(url) == expected


def test_the_client_and_the_live_call_use_it():
    from sergio_escritorio.call import ws_url

    assert SergioClient("http://localhost:8000").base == "http://127.0.0.1:8000"
    assert ws_url("http://localhost:8000").startswith("ws://127.0.0.1:8000")
