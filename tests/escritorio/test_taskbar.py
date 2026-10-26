"""Sergio pins to the taskbar as itself (taskbar.py)."""

from sergio_escritorio import taskbar


def test_the_window_identity_relaunches_sergio():
    props = taskbar.properties()
    assert list(props)[-1] == "id"  # relaunch keys first, then the ID
    assert props["id"] == taskbar.APP_ID == "Sergio.Asistente"
    assert props["relaunch_command"].endswith("-m sergio_escritorio")
    assert props["relaunch_name"] == "Sergio"


def test_property_keys_are_the_appusermodel_ones():
    fmtid, pid = taskbar.key("id")
    assert (fmtid.Data1, fmtid.Data2, fmtid.Data3) == (0x9F4C2855, 0x9F79, 0x4B39)
    assert bytes(fmtid.Data4) == bytes.fromhex("A8D0E1D42DE1D5F3")
    assert pid == 5 and taskbar.key("relaunch_command")[1] == 2


def test_off_windows_nothing_is_touched():
    assert taskbar.claim_process() is False
    assert taskbar.claim_window(1234) is False
