"""Feeds and backup listings cannot smuggle DOCTYPE or entity tricks."""

import pytest

from openjarvis.security import safe_xml


def test_plain_feeds_parse():
    root = safe_xml.fromstring(
        "<rss><channel><item><title>Hola</title></item></channel></rss>"
    )
    assert root.find("channel/item/title").text == "Hola"


@pytest.mark.parametrize(
    "evil",
    [
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><r>&lol;</r>',
        '<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>',
        "<! entity x 'y'><r/>",
    ],
)
def test_declarations_are_refused(evil):
    with pytest.raises(safe_xml.UnsafeXML):
        safe_xml.fromstring(evil)
    assert issubclass(safe_xml.UnsafeXML, ValueError)
