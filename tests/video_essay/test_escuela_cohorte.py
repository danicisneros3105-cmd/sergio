from openjarvis.video_essay import escuela


def test_hard_cut_can_keep_the_same_colour_histogram():
    import numpy as np

    a = np.zeros((24, 24, 3), dtype="uint8")
    a[:, :12] = 255
    b = a[:, ::-1].copy()
    assert escuela.cuts_of([a] * 15 + [b] * 15, fps=30) == [0.5]


def test_fixed_cohort_accepts_local_media_without_listing_or_upload(
    tmp_path, monkeypatch
):
    ids = [f"clip{i:07d}" for i in range(20)]
    media = tmp_path / "media"
    media.mkdir()
    for vid in ids[:-1]:
        (media / f"{vid}.mp4").touch()

    def unexpected(*_args, **_kwargs):
        raise AssertionError(
            "La tanda fija no debe pedir otra lista ni descargar archivos."
        )

    def measure(path, *, fps):
        assert path.parent == media and fps == 30
        return {"resumen": {"fps_medido": fps, "fotogramas_muestreados": 30}}

    def synthesize(category, *, refs, cohort, ask):
        assert len(cohort) == 20 and ask("cualquier prompt") == ""
        assert [escuela.video_id(v["url"]) for v in cohort] == ids
        return {"categoria": category}

    monkeypatch.setattr(escuela, "home", lambda: tmp_path / "escuela")
    monkeypatch.setattr(escuela, "channel_links", unexpected)
    monkeypatch.setattr(escuela, "download", unexpected)
    monkeypatch.setattr(escuela, "measure", measure)
    monkeypatch.setattr(escuela, "synthesize", synthesize)
    key = "shorts-animados"
    options = {"shorts_ids": ids, "shorts_media": media}
    partial = escuela.run_all([key], **options)["cohortes"][key]
    assert partial["medidos"] == 19 and not partial["perfil_actualizado"]
    (media / f"{ids[-1]}.mp4").touch()
    full = escuela.run_all([key], **options)["cohortes"][key]
    assert full["medidos"] == 20 and full["perfil_actualizado"]
    assert full["origen"] == "archivos_locales"


def test_channel_never_replaces_missing_shorts_with_other_uploads(tmp_path):
    calls = []

    def list_tab(args):
        calls.append(args[-1])
        return ""

    channel = escuela.references()["shorts-animados"]["canales"][0]
    assert not escuela.channel_links(channel, root=tmp_path, run=list_tab)
    assert calls == ["https://www.youtube.com/@RicksClips3000/shorts"]


def test_school_only_builds_profile_from_complete_current_cohort(tmp_path, monkeypatch):
    links = [f"https://www.youtube.com/watch?v=clip{i:07d}" for i in range(20)]
    stale = tmp_path / "shorts-animados" / "older.json"
    stale.parent.mkdir()
    stale.write_text("{}", encoding="utf-8")
    failed = {links[-1]}
    calls = []
    profiles = []

    def listed(channel, *, refresh):
        assert channel["pestana"] == "shorts" and refresh
        return links

    def study(url, category, *, fps, require_frames):
        assert fps == 30 and require_frames and category == "shorts-animados"
        calls.append(url)
        if url in failed:
            raise RuntimeError("no disponible")
        return {
            "url": url,
            "medido": {"resumen": {"fps_medido": 30, "fotogramas_muestreados": 690}},
        }

    def synthesize(category, *, refs, cohort):
        profiles.append([s["url"] for s in cohort])
        return {"categoria": category}

    monkeypatch.setattr(escuela, "home", lambda: tmp_path)
    monkeypatch.setattr(escuela, "channel_links", listed)
    monkeypatch.setattr(escuela, "study", study)
    monkeypatch.setattr(escuela, "synthesize", synthesize)
    key = "shorts-animados"
    partial = escuela.run_all([key])["cohortes"][key]
    assert partial["medidos"] == 19 and not partial["perfil_actualizado"]
    assert not profiles
    failed.clear()
    complete = escuela.run_all([key])["cohortes"][key]
    assert complete["completa"] and complete["perfil_actualizado"]
    assert profiles == [links] and calls == links * 2
    assert [v["url"] for v in complete["videos"]] == links
