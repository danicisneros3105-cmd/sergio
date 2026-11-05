"""Channels that post on their own: YouTube and Instagram, by their APIs.

The owner (27 Oct 2026): «que la gente cree una cuenta de YouTube y haga 3
videos diarios (videos TOP o shorts TOP) y los suba de forma automática…
o una cuenta de Instagram». What Sergio does, and what it does not:

* **The account is the person's.** They create it themselves (Google and
  Instagram verify a person with a phone; creating accounts by software is
  against both platforms' rules), then connect it once to Sergio (YouTube:
  Google sign-in with their own Google Cloud OAuth client; Instagram: a
  professional account and its Graph API token).
* **Posting is automatic when the owner turns it on** for a schedule
  (``publicar_en`` + ``auto``): a finished video goes up by the official
  APIs — YouTube Data API ``videos.insert`` (a Short when it is vertical and
  short: «#Shorts» in the title), Instagram Graph API Reels (container →
  status → ``media_publish``; the file is served once at a signed link on
  ``SERGIO_PUBLIC_URL``). At most ``SERGIO_PUBLICAR_DIA`` (3) posts a day per
  channel, so no account looks like spam. This replaces the old rule «never
  posted alone» only for the schedules where he turns it on.
* **People are never answered alone.** New comments on his videos are read
  and Sergio drafts a reply for each; they go out when he approves them
  (all at once with one tap). Automated replies to people are spam under
  both platforms' rules and his own rule (no automatic messages).

A YouTube project that Google has not audited uploads as *private* until it
passes the audit (Google's rule, not Sergio's): :func:`estado` says so.
Tokens are stored sealed (AES-GCM, :mod:`openjarvis.pagos.cifrado`) and 0600.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

YT_SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # read and answer comments
)
YT_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
YT_TOKEN = "https://oauth2.googleapis.com/token"
YT_UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
YT_API = "https://www.googleapis.com/youtube/v3"
IG_API = "https://graph.facebook.com/v21.0"
_LOCK = threading.Lock()


def _dir(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = get_config_dir()
    d = Path(home) / "canales"
    d.mkdir(parents=True, exist_ok=True)
    return d


def per_day() -> int:
    try:
        return max(1, min(10, int(os.environ.get("SERGIO_PUBLICAR_DIA", "3"))))
    except ValueError:
        return 3


# -- stored accounts (sealed) ----------------------------------------------------------


def _file(name: str, home: Optional[Path] = None) -> Path:
    return _dir(home) / f"{name}.json"


def save_account(name: str, data: Dict[str, Any], home: Optional[Path] = None) -> None:
    from openjarvis.pagos import cifrado

    sealed = cifrado.seal(json.dumps(data), aad=f"canal:{name}", home=home)
    path = _file(name, home)
    path.write_text(json.dumps({"sealed": sealed, "updated": time.time()}))
    os.chmod(path, 0o600)


def account(name: str, home: Optional[Path] = None) -> Dict[str, Any]:
    from openjarvis.pagos import cifrado

    path = _file(name, home)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        return json.loads(cifrado.unseal(raw["sealed"], aad=f"canal:{name}", home=home))
    except Exception:  # noqa: BLE001 — a damaged file is a disconnected account
        return {}


def forget(name: str, home: Optional[Path] = None) -> bool:
    path = _file(name, home)
    if path.exists():
        path.unlink()
        return True
    return False


# -- YouTube: connect once ---------------------------------------------------------------


def youtube_client(home: Optional[Path] = None) -> Dict[str, str]:
    """The owner's OAuth client (from Google Cloud: «Desktop app» or «Web»),
    from ``YOUTUBE_CLIENT_ID``/``YOUTUBE_CLIENT_SECRET`` or the JSON he
    downloaded, saved as ``~/.openjarvis/canales/youtube_client.json``."""
    cid = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    if cid and secret:
        return {"client_id": cid, "client_secret": secret}
    path = _dir(home) / "youtube_client.json"
    if path.exists():
        data = json.loads(path.read_text())
        data = data.get("installed") or data.get("web") or data
        return {
            "client_id": data.get("client_id", ""),
            "client_secret": data.get("client_secret", ""),
        }
    return {}


def youtube_connect_url(redirect: str, home: Optional[Path] = None) -> Dict[str, str]:
    """Where the owner signs in with Google to let Sergio post on his channel."""
    client = youtube_client(home)
    if not client.get("client_id"):
        raise RuntimeError(
            "Falta el cliente OAuth de Google: cree uno en Google Cloud (YouTube Data API v3) "
            "y ponga YOUTUBE_CLIENT_ID y YOUTUBE_CLIENT_SECRET en sergio.env."
        )
    state = secrets.token_urlsafe(16)
    (_dir(home) / "youtube_state").write_text(state)
    query = urllib.parse.urlencode({
        "client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(YT_SCOPES), "access_type": "offline", "prompt": "consent", "state": state,
    })  # fmt: skip
    return {"url": f"{YT_AUTH}?{query}", "state": state}


def youtube_finish(code: str, state: str, redirect: str, home: Optional[Path] = None,
                   http: Any = None) -> Dict[str, Any]:  # fmt: skip
    """The code Google sends back, exchanged for a refresh token (sealed)."""
    import hmac

    expected = (
        (_dir(home) / "youtube_state").read_text()
        if (_dir(home) / "youtube_state").exists()
        else ""
    )
    if not expected or not hmac.compare_digest(expected, state or ""):
        raise RuntimeError("La conexión no coincide: vuelva a intentarlo desde Sergio.")
    client = youtube_client(home)
    http = http or _http()
    resp = http.post(YT_TOKEN, data={
        "code": code, "client_id": client["client_id"], "client_secret": client["client_secret"],
        "redirect_uri": redirect, "grant_type": "authorization_code",
    })  # fmt: skip
    data = resp.json()
    if "refresh_token" not in data:
        raise RuntimeError(
            f"Google no dio permiso: {data.get('error_description') or data.get('error')}"
        )
    acc = {"refresh_token": data["refresh_token"], "access_token": data.get("access_token", ""),
           "expires": time.time() + float(data.get("expires_in", 0)) - 60, "hoy": "", "subidos_hoy": 0}  # fmt: skip
    channel = _yt_channel(acc, http, home)
    acc["canal"] = channel
    save_account("youtube", acc, home)
    (_dir(home) / "youtube_state").unlink(missing_ok=True)
    return {"conectado": True, "canal": channel}


def _http() -> Any:
    import httpx

    return httpx.Client(timeout=httpx.Timeout(120, connect=10))


def _yt_token(acc: Dict[str, Any], http: Any, home: Optional[Path]) -> str:
    if acc.get("access_token") and float(acc.get("expires") or 0) > time.time():
        return acc["access_token"]
    client = youtube_client(home)
    resp = http.post(YT_TOKEN, data={
        "client_id": client["client_id"], "client_secret": client["client_secret"],
        "refresh_token": acc["refresh_token"], "grant_type": "refresh_token",
    })  # fmt: skip
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"YouTube pidió volver a conectar: {data.get('error')}")
    acc["access_token"] = data["access_token"]
    acc["expires"] = time.time() + float(data.get("expires_in", 3600)) - 60
    save_account("youtube", acc, home)
    return acc["access_token"]


def _yt_channel(acc: Dict[str, Any], http: Any, home: Optional[Path]) -> Dict[str, str]:
    try:
        token = (
            _yt_token(acc, http, home)
            if acc.get("refresh_token")
            else acc.get("access_token", "")
        )
        resp = http.get(f"{YT_API}/channels", params={"part": "snippet", "mine": "true"},
                        headers={"Authorization": f"Bearer {token}"})  # fmt: skip
        item = (resp.json().get("items") or [{}])[0]
        return {
            "id": item.get("id", ""),
            "nombre": (item.get("snippet") or {}).get("title", ""),
        }
    except Exception:  # noqa: BLE001
        return {"id": "", "nombre": ""}


def _count_today(acc: Dict[str, Any]) -> int:
    today = time.strftime("%Y-%m-%d")
    if acc.get("hoy") != today:
        acc["hoy"], acc["subidos_hoy"] = today, 0
    return int(acc.get("subidos_hoy") or 0)


def is_short(aspect: str, seconds: float) -> bool:
    return aspect == "9:16" and seconds <= 180


def youtube_upload(
    video: Path,
    title: str,
    description: str,
    *,
    tags: Optional[List[str]] = None,
    short: bool = False,
    privacy: str = "public",
    home: Optional[Path] = None,
    http: Any = None,
) -> Dict[str, Any]:
    """One video up to the connected channel (resumable upload)."""
    acc = account("youtube", home)
    if not acc.get("refresh_token"):
        raise RuntimeError("YouTube no está conectado.")
    if _count_today(acc) >= per_day():
        raise RuntimeError(
            f"Hoy ya se subieron {per_day()} videos a YouTube (SERGIO_PUBLICAR_DIA)."
        )
    http = http or _http()
    token = _yt_token(acc, http, home)
    if short and "#shorts" not in (title + description).lower():
        title = (title[:90] + " #Shorts").strip()
    body = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": (tags or [])[:30],
                    "categoryId": "22"},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},
    }  # fmt: skip
    start = http.post(
        YT_UPLOAD, params={"uploadType": "resumable", "part": "snippet,status"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(video.stat().st_size)},
        content=json.dumps(body),
    )  # fmt: skip
    where = start.headers.get("location") or start.headers.get("Location")
    if not where:
        raise RuntimeError(
            f"YouTube no aceptó la subida: {str(getattr(start, 'text', ''))[:200]}"
        )
    done = http.put(where, headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"},
                    content=video.read_bytes())  # fmt: skip
    data = done.json()
    if not data.get("id"):
        raise RuntimeError(f"YouTube no terminó la subida: {str(data)[:200]}")
    acc["subidos_hoy"] = _count_today(acc) + 1
    save_account("youtube", acc, home)
    status = (data.get("status") or {}).get("privacyStatus", privacy)
    return {"canal": "youtube", "id": data["id"], "url": f"https://youtu.be/{data['id']}",
            "privacidad": status, "short": short}  # fmt: skip


def youtube_thumbnail(video_id: str, cover: Path, *, short: bool, http: Any = None) -> str:
    """Apply a JPEG cover to a video already received by YouTube."""
    http = http or _http()
    token = _yt_token(account("youtube"), http, None)
    headers = {"Authorization": f"Bearer {token}"}
    if short:
        result = http.get(f"{YT_API}/videos", params={"id": video_id, "part": "processingDetails"}, headers=headers)
        result.raise_for_status()
        items = result.json().get("items") or [{}]
        if (items[0].get("processingDetails") or {}).get("processingStatus") != "succeeded":
            return "procesando"
    with cover.open("rb") as body:
        result = http.post(
            "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
            params={"videoId": video_id, "uploadType": "media"},
            headers={**headers, "Content-Type": "image/jpeg"},
            content=body.read(2 * 1024 * 1024 + 1),
        )
    result.raise_for_status()
    return "aplicada"


# -- Instagram (professional account, Graph API) ----------------------------------------------


def instagram_connect(
    user_id: str, token: str, home: Optional[Path] = None, http: Any = None
) -> Dict[str, Any]:
    """His Instagram professional account id and a long-lived token (from
    Meta's developer app, with instagram_content_publish)."""
    http = http or _http()
    resp = http.get(
        f"{IG_API}/{user_id}", params={"fields": "username", "access_token": token}
    )
    data = resp.json()
    if "username" not in data:
        raise RuntimeError(
            f"Instagram no aceptó la cuenta: {(data.get('error') or {}).get('message', data)}"
        )
    save_account("instagram", {"user_id": user_id, "token": token, "usuario": data["username"],
                               "hoy": "", "subidos_hoy": 0}, home)  # fmt: skip
    return {"conectado": True, "usuario": data["username"]}


_SHARED: Dict[str, Path] = {}  # one-time links: token -> file


def share_once(path: Path) -> str:
    """A link Instagram can fetch the file from once (``SERGIO_PUBLIC_URL``)."""
    base = os.environ.get("SERGIO_PUBLIC_URL", "").rstrip("/")
    if not base.startswith("https://"):
        raise RuntimeError(
            "Instagram necesita SERGIO_PUBLIC_URL con https (el túnel de Sergio)."
        )
    token = secrets.token_urlsafe(24)
    _SHARED[token] = path
    return f"{base}/v1/automatiza/archivo/{token}"


def take_shared(token: str) -> Optional[Path]:
    return _SHARED.pop(token, None)


def instagram_publish(video: Path, caption: str, *, home: Optional[Path] = None, http: Any = None,
                      wait: Callable[[float], None] = time.sleep) -> Dict[str, Any]:  # fmt: skip
    acc = account("instagram", home)
    if not acc.get("token"):
        raise RuntimeError("Instagram no está conectado.")
    if _count_today(acc) >= per_day():
        raise RuntimeError(
            f"Hoy ya se publicaron {per_day()} Reels (SERGIO_PUBLICAR_DIA)."
        )
    http = http or _http()
    uid, token = acc["user_id"], acc["token"]
    made = http.post(
        f"{IG_API}/{uid}/media",
        data={
            "media_type": "REELS",
            "video_url": share_once(video),
            "caption": caption[:2200],
            "access_token": token,
        },
    ).json()
    container = made.get("id")
    if not container:
        raise RuntimeError(
            f"Instagram no aceptó el video: {(made.get('error') or {}).get('message', made)}"
        )
    for _ in range(40):  # Instagram processes the video first
        st = http.get(
            f"{IG_API}/{container}",
            params={"fields": "status_code", "access_token": token},
        ).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError("Instagram no pudo procesar el video.")
        wait(15)
    pub = http.post(
        f"{IG_API}/{uid}/media_publish",
        data={"creation_id": container, "access_token": token},
    ).json()
    if not pub.get("id"):
        raise RuntimeError(
            f"Instagram no publicó: {(pub.get('error') or {}).get('message', pub)}"
        )
    acc["subidos_hoy"] = _count_today(acc) + 1
    save_account("instagram", acc, home)
    return {"canal": "instagram", "id": pub["id"]}


def instagram_story(media: Path, *, home: Optional[Path] = None, http: Any = None,
                    wait: Callable[[float], None] = time.sleep) -> Dict[str, Any]:  # fmt: skip
    """A photo or a video as an Instagram story (Graph API, media_type STORIES).

    Only for the owner's Business/Creator account he connected; the caller asks
    for his yes first (publishing is never automatic)."""
    acc = account("instagram", home)
    if not acc.get("token"):
        raise RuntimeError("Instagram no está conectado.")
    http = http or _http()
    uid, token = acc["user_id"], acc["token"]
    video = media.suffix.lower() in (".mp4", ".mov", ".m4v")
    data = {"media_type": "STORIES", "access_token": token}
    data["video_url" if video else "image_url"] = share_once(media)
    made = http.post(f"{IG_API}/{uid}/media", data=data).json()
    container = made.get("id")
    if not container:
        raise RuntimeError(
            f"Instagram no aceptó la historia: {(made.get('error') or {}).get('message', made)}"
        )
    for _ in range(40 if video else 0):  # a video is processed first
        st = http.get(
            f"{IG_API}/{container}",
            params={"fields": "status_code", "access_token": token},
        ).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError("Instagram no pudo procesar la historia.")
        wait(10)
    pub = http.post(
        f"{IG_API}/{uid}/media_publish",
        data={"creation_id": container, "access_token": token},
    ).json()
    if not pub.get("id"):
        raise RuntimeError(
            f"Instagram no publicó la historia: {(pub.get('error') or {}).get('message', pub)}"
        )
    return {"canal": "instagram", "historia": pub["id"]}


# -- comments: read, draft, send when approved ---------------------------------------------


def youtube_comments(
    home: Optional[Path] = None, http: Any = None, limit: int = 20
) -> List[Dict[str, str]]:
    """The newest comments on his channel's videos that he has not answered."""
    acc = account("youtube", home)
    channel = (acc.get("canal") or {}).get("id")
    if not channel:
        return []
    http = http or _http()
    token = _yt_token(acc, http, home)
    data = http.get(f"{YT_API}/commentThreads", params={
        "part": "snippet", "allThreadsRelatedToChannelId": channel, "maxResults": limit, "order": "time",
    }, headers={"Authorization": f"Bearer {token}"}).json()  # fmt: skip
    out = []
    for item in data.get("items") or []:
        top = (item.get("snippet") or {}).get("topLevelComment") or {}
        sn = top.get("snippet") or {}
        if (item.get("snippet") or {}).get("totalReplyCount", 0):
            continue
        out.append({"id": top.get("id", ""), "video": sn.get("videoId", ""),
                    "autor": sn.get("authorDisplayName", ""), "texto": sn.get("textOriginal", "")})  # fmt: skip
    return out


REPLY_PROMPT = """You answer comments on the owner's YouTube channel, as the channel. \
Reply in the comment's language, warm, brief (max 2 sentences), specific to what they said, \
no links, no self-promotion, no emojis spam. Comments (JSON): {comments}
Answer ONLY JSON: {{"replies": [{{"id": "comment id", "reply": "text"}}]}}"""


def draft_replies(comments: List[Dict[str, str]], ask: Optional[Callable[..., str]] = None,
                  home: Optional[Path] = None) -> List[Dict[str, str]]:  # fmt: skip
    """A reply drafted for each comment, kept for his approval."""
    if not comments:
        return []
    plain = ask  # a plain-text call for polishing (the default one answers JSON)
    if ask is None:
        from openjarvis.creator.llm import ask as llm_ask

        def ask(p: str, **kw: Any) -> str:
            return llm_ask(p, json_mode=True, max_tokens=4000)

        def plain(p: str, **kw: Any) -> str:
            return llm_ask(p, max_tokens=600)

    data = json.loads(
        ask(
            REPLY_PROMPT.format(
                comments=json.dumps(comments, ensure_ascii=False)[:12000]
            )
        )
    )
    from openjarvis.automatiza import humano

    by_id = {c["id"]: c for c in comments}
    drafts: List[Dict[str, str]] = []
    said: List[str] = []
    for r in data.get("replies") or []:
        if r.get("id") not in by_id or not r.get("reply"):
            continue
        # not ten replies that all open the same way (4 Nov 2026)
        text = humano.polish(str(r["reply"])[:500], plain, said[-10:])
        said.append(text)
        drafts.append({**by_id[r["id"]], "respuesta": text[:500]})
    path = _dir(home) / "respuestas.json"
    with _LOCK:
        old = json.loads(path.read_text()) if path.exists() else []
        known = {d["id"] for d in old}
        path.write_text(
            json.dumps(
                old + [d for d in drafts if d["id"] not in known], ensure_ascii=False
            )
        )
    return drafts


def pending_replies(home: Optional[Path] = None) -> List[Dict[str, str]]:
    path = _dir(home) / "respuestas.json"
    return json.loads(path.read_text()) if path.exists() else []


def send_replies(ids: List[str], home: Optional[Path] = None, http: Any = None) -> int:
    """Send the replies HE approved (ids), and only those."""
    acc = account("youtube", home)
    http = http or _http()
    token = _yt_token(acc, http, home)
    sent = 0
    with _LOCK:
        path = _dir(home) / "respuestas.json"
        drafts = json.loads(path.read_text()) if path.exists() else []
        keep = []
        for d in drafts:
            if d["id"] not in ids:
                keep.append(d)
                continue
            resp = http.post(f"{YT_API}/comments", params={"part": "snippet"},
                             headers={"Authorization": f"Bearer {token}"},
                             json={"snippet": {"parentId": d["id"], "textOriginal": d["respuesta"]}})  # fmt: skip
            if int(getattr(resp, "status_code", 200)) >= 400:
                keep.append(d)  # refused: it stays for another try
                continue
            sent += 1
        path.write_text(json.dumps(keep, ensure_ascii=False))
    return sent


# -- automatic posting of finished scheduled videos ------------------------------------------


def post_ready(
    home: Optional[Path] = None,
    root: Optional[Path] = None,
    uploaders: Optional[Dict[str, Callable[..., Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Post the finished videos of the schedules he set to «auto» (once each)."""
    from openjarvis.video_essay import job as jobs
    from openjarvis.video_essay import schedule

    ups = uploaders or {"youtube": youtube_upload, "instagram": instagram_publish}
    auto = {
        j: s
        for s in schedule.load(home)
        if s.get("auto")
        for j in s.get("hechos") or []
    }
    done: List[Dict[str, Any]] = []
    for job in jobs.all_jobs(root):
        item = auto.get(job.id)
        st = job.state()
        if item is None or st.get("status") != "listo" or st.get("publicado"):
            continue
        res = st.get("result") or {}
        video = Path(res.get("path") or res.get("video") or "")
        if not video.exists():
            continue
        pkg = res.get("package") or {}
        title = pkg.get("title") or (st.get("title") or "Video")
        text = pkg.get("description") or ""
        tags = list(pkg.get("tags") or [])
        short = is_short(item.get("formato", ""), float(item.get("segundos") or 60))
        # A channel that already took this video is never posted to again
        # (if Instagram failed, the next pass retries only Instagram).
        posted: Dict[str, Any] = dict(st.get("publicado_parcial") or {})
        for channel in item.get("publicar_en") or []:
            if channel in posted and "error" not in posted[channel]:
                continue
            try:
                if channel == "youtube":
                    posted[channel] = ups[channel](
                        video, title, text, tags=tags, short=short, home=home
                    )
                elif channel == "instagram":
                    tagline = " ".join("#" + t.replace(" ", "") for t in tags[:5])
                    posted[channel] = ups[channel](
                        video, f"{title}\n\n{text}\n{tagline}".strip(), home=home
                    )
            except Exception as exc:  # noqa: BLE001 — said in the job, tried next time
                posted[channel] = {"error": str(exc)[:200]}
        if posted and all("error" not in v for v in posted.values()):
            job.update(publicado={"cuando": time.time(), **posted})
        else:
            ok = {k: v for k, v in posted.items() if "error" not in v}
            job.update(publicacion_error=posted, publicado_parcial=ok)
        done.append({"job": job.id, **posted})
    return done


def estado(home: Optional[Path] = None) -> Dict[str, Any]:
    yt, ig = account("youtube", home), account("instagram", home)
    return {
        "youtube": {"conectado": bool(yt.get("refresh_token")), "canal": (yt.get("canal") or {}).get("nombre", ""),
                    "cliente_oauth": bool(youtube_client(home).get("client_id")),
                    "nota": "Sin auditoría de Google, los videos suben como privados."},
        "instagram": {"conectado": bool(ig.get("token")), "usuario": ig.get("usuario", ""),
                      "enlace_publico": os.environ.get("SERGIO_PUBLIC_URL", "").startswith("https://")},
        "por_dia": per_day(),
        "respuestas_pendientes": len(pending_replies(home)),
    }  # fmt: skip


__all__ = [
    "account",
    "instagram_story",
    "draft_replies",
    "estado",
    "forget",
    "instagram_connect",
    "instagram_publish",
    "is_short",
    "pending_replies",
    "per_day",
    "post_ready",
    "save_account",
    "send_replies",
    "share_once",
    "take_shared",
    "youtube_comments",
    "youtube_connect_url",
    "youtube_finish",
    "youtube_thumbnail",
    "youtube_upload",
]
