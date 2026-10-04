"""Opening apps at once, by the name people say, on the screen in use."""

import json

import pytest
from sergio_escritorio.apps import (
    App,
    AppIndex,
    Launcher,
    Window,
    scan_shortcuts,
    scan_start_apps,
    score,
)

START = [
    App("Spotify", "appid", "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"),
    App("Calculadora", "appid", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
    App("Bloc de notas", "appid", "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"),
    App("Word", "lnk", r"C:\ProgramData\...\Word.lnk"),
    App("Google Chrome", "lnk", r"C:\ProgramData\...\Google Chrome.lnk"),
    App("Uninstall Spotify", "lnk", r"C:\...\Uninstall Spotify.lnk"),
    App("WhatsApp", "appid", "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"),
    App("Visual Studio Code", "lnk", r"C:\...\Visual Studio Code.lnk"),
    App("Blender 4.2", "lnk", r"C:\...\Blender 4.2.lnk"),
    App("Configuración", "appid", "windows.immersivecontrolpanel_cw5n1h2txyewy!x"),
]


@pytest.mark.parametrize(
    "said, expected",
    [
        ("spotify", "Spotify"),
        ("la calculadora", "Calculadora"),
        ("bloc de notas", "Bloc de notas"),
        ("el word", "Word"),
        ("chrome", "Google Chrome"),
        ("whatsapp", "WhatsApp"),
        ("vs code", "Visual Studio Code"),
        ("blender", "Blender 4.2"),
        ("configuracion", "Configuración"),
        ("ajustes", "Configuración"),
    ],
)
def test_names_as_people_say_them(said, expected):
    assert AppIndex(START).find(said).name == expected


def test_uninstallers_and_unknown_apps_are_never_picked():
    index = AppIndex(START)
    assert all("Uninstall" not in a.name for a in index.apps)
    assert index.find("photoshop") is None
    assert score("excel", "Spotify") == 0


class FakeDesktop:
    def __init__(self, windows=(), appear=None, after=2):
        self.now = list(windows)
        self.appear = appear  # window that shows up after a few looks
        self.after = after
        self.looks = 0
        self.launched, self.uris, self.front, self.closed = [], [], [], []

    def windows(self):
        self.looks += 1
        if (
            self.appear is not None
            and self.looks > self.after
            and self.appear not in self.now
        ):
            self.now.append(self.appear)
        return list(self.now)

    def launch(self, app):
        self.launched.append(app)

    def open_uri(self, uri):
        self.uris.append(uri)

    def start_program(self, names):
        return False

    def to_front_here(self, hwnd):
        self.front.append(hwnd)

    def close(self, hwnd):
        self.closed.append(hwnd)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def launcher(desktop, index=None):
    clock = Clock()
    return Launcher(
        AppIndex(START) if index is None else index,
        desktop,
        sleep=clock.sleep,
        clock=clock,
        rescan=lambda: AppIndex(START),
    )


def test_open_launches_directly_and_brings_the_new_window_here():
    spotify = Window(77, "Spotify Free", "spotify")
    desk = FakeDesktop([Window(1, "Documento - Word", "winword")], appear=spotify)
    result = launcher(desk).open("spotify")
    assert result == "opened Spotify"
    assert desk.launched[0].kind == "appid"  # no typing into the Start menu
    assert desk.front == [77]  # moved to your monitor and focused


def test_already_open_app_is_brought_to_the_front():
    desk = FakeDesktop([Window(5, "Song name - Artist", "spotify")])
    assert launcher(desk).open("spotify") == "opened Spotify"
    assert desk.front == [5]


def test_slow_apps_report_they_are_starting():
    desk = FakeDesktop([])
    assert "still starting" in launcher(desk).open("blender", wait=0.3)


def test_system_apps_by_link_when_not_in_the_list():
    desk = FakeDesktop(
        [], appear=Window(9, "Alarmas y reloj", "applicationframehost"), after=0
    )
    launcher(desk, AppIndex([])).open("reloj")
    assert desk.uris == ["ms-clock:"]


def test_unknown_app_is_a_clear_error():
    with pytest.raises(LookupError, match="No encuentro"):
        launcher(FakeDesktop([]), AppIndex([])).open("ninguna app rara")


def test_close_by_program_not_by_a_lookalike_title():
    desk = FakeDesktop(
        [
            Window(1, "how to use word - Google Chrome", "chrome"),
            Window(2, "Informe.docx - Word", "winword"),
            Window(3, "Sergio", "python"),
        ]
    )
    closed = launcher(desk).close("word")
    assert desk.closed == [2] and closed == ["Informe.docx - Word"]


def test_close_spotify_titled_with_the_song():
    desk = FakeDesktop([Window(4, "Bad Bunny - Monaco", "spotify")])
    assert launcher(desk).close("spotify") == ["Bad Bunny - Monaco"]


def test_scans(tmp_path):
    programs = tmp_path / "Programs" / "Accesorios"
    programs.mkdir(parents=True)
    (programs / "Paint.lnk").write_bytes(b"")
    (programs / "notes.txt").write_text("x")
    assert [a.name for a in scan_shortcuts([tmp_path / "Programs"])] == ["Paint"]
    out = json.dumps(
        [{"Name": "Spotify", "AppID": "Spotify!App"}, {"Name": "", "AppID": "x"}]
    )
    apps = scan_start_apps(run=lambda cmd: out)
    assert apps == [App("Spotify", "appid", "Spotify!App")]
    single = json.dumps({"Name": "Fotos", "AppID": "Photos!App"})
    assert scan_start_apps(run=lambda cmd: single)[0].name == "Fotos"


def test_index_cache_round_trip(tmp_path):
    path = tmp_path / "apps.json"
    AppIndex(START).save(path)
    assert AppIndex.load(path).find("spotify").target.endswith("!Spotify")


def test_spanish_names_with_articles_reach_the_tables():
    from sergio_escritorio.apps import ALIASES, URI_APPS, lookup

    assert lookup(URI_APPS, "bloc de notas") == "notepad.exe"
    assert lookup(URI_APPS, "el Bloc de Notas") == "notepad.exe"
    assert lookup(ALIASES, "la calculadora") == ["calculator", "calc"]


def test_notepad_opens_even_when_the_start_menu_list_is_empty():
    desk = FakeDesktop([], appear=Window(3, "Sin título: Bloc de notas", "notepad"), after=0)
    empty = launcher(desk, AppIndex([]))
    empty._rescan = lambda: AppIndex([])  # the scan found nothing on this PC
    assert empty.open("bloc de notas") == "opened bloc de notas"
    assert desk.uris == ["notepad.exe"] and desk.front == [3]


def test_start_apps_falls_back_to_the_apps_folder():
    seen = []

    def run(cmd):
        seen.append(cmd[-1])
        return "" if len(seen) == 1 else json.dumps([{"Name": "Bloc de notas", "AppID": "Notepad!App"}])

    assert scan_start_apps(run=run)[0].name == "Bloc de notas" and "AppsFolder" in seen[1]
