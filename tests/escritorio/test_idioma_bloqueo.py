"""Sergio international (language, country, crisis lines) and blocking."""

from __future__ import annotations

from types import SimpleNamespace

from sergio_escritorio import bloqueo, idioma


def test_every_country_has_its_own_lines_and_a_source():
    for code, c in idioma.COUNTRIES.items():
        assert c.emergency and c.crisis and c.source.startswith("https://"), code
    assert "988" in idioma.crisis_line("US") and "024" in idioma.crisis_line("ES")
    assert "171" in idioma.crisis_line("EC") and "*4141" in idioma.crisis_line("CL")
    assert "findahelpline" in idioma.crisis_line("XX")  # anywhere else


def test_the_crisis_message_is_in_the_users_language_with_their_numbers():
    text = idioma.crisis_text("GB", "en")
    assert "999" in text and "116 123" in text and "I'm here" in text
    assert "Línea 113" in idioma.crisis_text("PE", "es")


def test_risk_is_heard_in_every_language():
    for said in ("quiero morir", "I want to die", "quero morrer", "envie de mourir", "voglio morire"):
        assert idioma.at_risk(said), said
    assert not idioma.at_risk("me muero de risa con este video")


def test_language_and_country_by_voice():
    assert idioma.language_asked("Sergio, habla en inglés") == "en"
    assert idioma.language_asked("speak in french") == "fr"
    assert idioma.language_asked("el inglés es difícil") == ""
    assert idioma.country_said("estoy en México") == "MX"
    assert idioma.country_said("vivo en Estados Unidos") == "US"
    assert idioma.country_said("estoy en la oficina") == ""


def test_the_interface_speaks_six_languages():
    assert idioma.t("tab_all", "en") == "All" and idioma.t("tab_settings", "de") == "Einstellungen"
    assert idioma.t("cams", "pt") == "Câmeras ao vivo"
    assert all(set(table) == set(idioma.UI_LANGUAGES) for table in idioma.TEXTS.values())
    assert "Spanish" not in idioma.speak_rule("en") and "«sir»" in idioma.speak_rule("en")


def test_what_people_say_becomes_programs_and_sites():
    assert bloqueo.program("Discord") == "discord.exe"
    assert bloqueo.program("configuración") == "systemsettings.exe"
    assert bloqueo.site("https://www.YouTube.com/") == "youtube.com" and bloqueo.site("tiktok") == "tiktok.com"
    assert bloqueo.parse_block("bloquea youtube.com") == ("sites", "youtube.com")
    assert bloqueo.parse_block("bloquea la app Steam") == ("apps", "Steam")
    assert bloqueo.parse_block("bloquea búsquedas de casino") == ("words", "casino")
    assert bloqueo.parse_block("bloquea la computadora") is None


def test_windows_itself_can_never_be_blocked(tmp_path):
    store = bloqueo.Store(tmp_path / "b.json")
    assert store.list.add("apps", "explorer.exe") == ""
    assert store.list.add("apps", "taskmgr") == ""


class Proc:
    def __init__(self, name):
        self.info = {"name": name}
        self.killed = False

    def terminate(self):
        self.killed = True


def test_the_guard_closes_blocked_apps_and_searches_only_while_on(tmp_path):
    store = bloqueo.Store(tmp_path / "b.json")
    store.list.add("apps", "Discord")
    store.list.add("words", "casino")
    procs = [Proc("Discord.exe"), Proc("explorer.exe"), Proc("chrome.exe")]
    tabs = []
    guard = bloqueo.Guard(store, processes=lambda: procs, title=lambda: "casino online - Buscar con Google",
                          close_tab=lambda: tabs.append(1))
    assert guard.check() == [] and not procs[0].killed  # off: nothing happens
    store.list.on = True
    assert guard.check() == ["discord.exe", "búsqueda"]
    assert procs[0].killed and not procs[1].killed and tabs == [1]


class FakeRegistry(SimpleNamespace):
    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self):
        super().__init__(keys={})

    def CreateKey(self, _root, path):  # noqa: N802
        return self.keys.setdefault(path, {})

    def EnumValue(self, key, i):  # noqa: N802
        names = list(key)
        if i >= len(names):
            raise OSError
        return (names[i], key[names[i]], 1)

    def DeleteValue(self, key, name):  # noqa: N802
        del key[name]

    def SetValueEx(self, key, name, _r, _t, value):  # noqa: N802
        key[name] = value

    def CloseKey(self, _key):  # noqa: N802
        pass


def test_websites_use_each_browsers_own_policy_and_are_cleared(tmp_path):
    reg = FakeRegistry()
    store = bloqueo.Store(tmp_path / "b.json")
    store.list.add("sites", "youtube.com")
    store.list.add("sites", "tiktok.com")
    said = bloqueo.switch_on(store, reg)
    assert "Chrome" in said and reg.keys[bloqueo.BROWSERS["Edge"]] == {"1": "youtube.com", "2": "tiktok.com"}
    assert bloqueo.switch_off(store, approved=False, registry=reg).startswith("Solo el dueño")
    assert store.list.on
    bloqueo.switch_off(store, approved=True, registry=reg)
    assert not store.list.on and reg.keys[bloqueo.BROWSERS["Chrome"]] == {}
    assert not bloqueo.Store(tmp_path / "b.json").list.on  # saved


def test_every_country_and_many_languages():
    from sergio_escritorio.panel import all_territories

    codes = dict(all_territories())
    assert len(codes) > 240 and "JP" in codes and "KE" in codes
    assert idioma.crisis_line("JP").startswith("110 / 119")
    assert "112" in idioma.crisis_line("GT") and "confirme" in idioma.crisis_line("GT")
    assert len(idioma.LANGUAGES) > 30 and "Japanese" in idioma.speak_rule("ja")
    assert idioma.t("tab_all", "ja") == "All"  # interface falls back to English
