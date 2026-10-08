"""Video Pro's post-production: masters, colour, AI frame interpolation,
silence cutting and Python effects — one orchestrated pipeline.

* ``cut_silences``: auto-editor removes the dead air of talking clips
  before the editor plans the cut.
* ``interpolate``: AI frame interpolation with RIFE (rife-ncnn-vulkan, on the
  graphics card, or the processor without one): 60 fps, or smooth slow
  motion. Without RIFE, ffmpeg's motion-compensated ``minterpolate``.
* ``master_command``: the deliverables a colourist or editor expects —
  Apple ProRes 422 HQ or Avid DNxHR HQX (10-bit 4:2:2, PCM 24-bit audio)
  for DaVinci / Premiere / Avid, and HEVC 10-bit for delivery — with a
  colour chain (3D LUT, denoise, sharpen, curves, learned grade) processed
  in 10 bits so gradients do not band.
* ``ken_burns``: photos become clips with a slow push (MoviePy when it is
  installed, ffmpeg otherwise), so a folder of photos edits like video.
* ``pipeline``: silences -> plan and cut (``video_pro``) -> interpolation
  -> master, every step logged.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from sergio_escritorio.media import HOME, ffmpeg, probe

# What each master is, and the ffmpeg settings that make it.
MASTERS: dict[str, dict[str, Any]] = {
    "prores": {
        "label": "Apple ProRes 422 HQ, 10 bits",
        "ext": ".mov",
        "video": ["-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0", "-pix_fmt", "yuv422p10le"],
        "audio": ["-c:a", "pcm_s24le"],
    },
    "prores4444": {
        "label": "Apple ProRes 4444, 10 bits (con alfa)",
        "ext": ".mov",
        "video": ["-c:v", "prores_ks", "-profile:v", "4", "-vendor", "apl0", "-pix_fmt", "yuva444p10le"],
        "audio": ["-c:a", "pcm_s24le"],
    },
    "dnxhr": {
        "label": "Avid DNxHR HQX, 10 bits",
        "ext": ".mov",
        "video": ["-c:v", "dnxhd", "-profile:v", "dnxhr_hqx", "-pix_fmt", "yuv422p10le"],
        "audio": ["-c:a", "pcm_s24le"],
    },
    "hevc10": {
        "label": "HEVC (H.265) 10 bits para entregar",
        "ext": ".mp4",
        "video": ["-c:v", "libx265", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p10le",
                  "-tag:v", "hvc1", "-x265-params", "log-level=error"],
        "audio": ["-c:a", "aac", "-b:a", "256k"],
    },
}
REC709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
RIFE_URL = "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-{os}.zip"
RIFE_MODEL = "rife-v4.6"
TOOLS = HOME / "tools"


# -- colour ---------------------------------------------------------------------
def color_chain(
    *,
    lut: str = "",
    denoise: bool = False,
    sharpen: bool = False,
    contrast_curve: bool = False,
    grade: str = "",
) -> str:
    """The colour filters, in 10-bit 4:4:4 so nothing bands: denoise first,
    then the LUT (a .cube from the colourist or a film look), the curve,
    the learned grade, and sharpening last."""
    steps = ["format=yuv444p10le"]
    if denoise:
        steps.append("hqdn3d=1.5:1.5:6:6")
    if lut:
        path = lut.replace("\\", "/").replace(":", "\\\\:")
        steps.append(f"lut3d=file='{path}':interp=tetrahedral")
    if contrast_curve:
        steps.append("curves=preset=medium_contrast")
    if grade:
        steps.append(grade)
    if sharpen:
        steps.append("unsharp=5:5:0.6:5:5:0.0")
    return ",".join(steps)


def master_command(src: Path, out: Path, kind: str = "prores", *, color: str = "", exe: str = "ffmpeg") -> list[str]:
    """One master of *src*: ProRes / DNxHR / HEVC 10-bit, Rec.709 tagged."""
    spec = MASTERS[kind]
    chain = color or "format=yuv444p10le"
    return [
        exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
        "-vf", chain, *spec["video"], *REC709, *spec["audio"], "-movflags", "+faststart", str(out),
    ]


def master(src: Path, kind: str = "prores", *, color: str = "", out: Path | None = None) -> Path:
    out = out or src.with_name(f"{src.stem}-master-{kind}{MASTERS[kind]['ext']}")
    done = subprocess.run(master_command(src, out, kind, color=color, exe=ffmpeg()), capture_output=True, text=True,
                          check=False)
    if done.returncode != 0 or not out.exists():
        raise RuntimeError("El máster falló: " + done.stderr[-400:])
    return out


# -- AI frame interpolation (RIFE) ---------------------------------------------------
def find_rife() -> Path | None:
    """rife-ncnn-vulkan, installed by Sergio or on the PATH."""
    name = "rife-ncnn-vulkan.exe" if os.name == "nt" else "rife-ncnn-vulkan"
    for found in TOOLS.glob(f"rife-ncnn-vulkan-*/{name}"):
        return found
    on_path = shutil.which("rife-ncnn-vulkan")
    return Path(on_path) if on_path else None


def install_rife(download: Callable[[str, Path], None] | None = None) -> Path:
    """Download RIFE (the official release, ~400 MB with its models) once."""
    found = find_rife()
    if found:
        return found
    TOOLS.mkdir(parents=True, exist_ok=True)
    url = RIFE_URL.format(os="windows" if os.name == "nt" else "ubuntu")
    archive = TOOLS / "rife.zip"
    if download is None:
        import httpx

        with httpx.stream("GET", url, follow_redirects=True, timeout=600) as resp, archive.open("wb") as fh:
            resp.raise_for_status()
            for chunk in resp.iter_bytes(1 << 20):
                fh.write(chunk)
    else:
        download(url, archive)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(TOOLS)
    archive.unlink(missing_ok=True)
    found = find_rife()
    if found is None:
        raise RuntimeError("No pude instalar RIFE.")
    if os.name != "nt":
        found.chmod(0o755)
    return found


def rife_command(rife: Path, frames_in: Path, frames_out: Path, count: int, gpu: bool = True) -> list[str]:
    cmd = [str(rife), "-i", str(frames_in), "-o", str(frames_out), "-m", RIFE_MODEL, "-n", str(count), "-f", "%08d.png"]
    if not gpu:
        cmd += ["-g", "-1", "-j", "1:2:2"]
    return cmd


def minterpolate_filter(fps: int) -> str:
    """ffmpeg's motion-compensated interpolation (no AI): the fallback."""
    return f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"


def interpolate(src: Path, out: Path | None = None, *, fps: int = 60, slow: float = 1.0,
                engine: str = "auto", gpu: bool = True) -> tuple[Path, str]:
    """More frames between frames: *fps* output (60 = smooth motion) and
    *slow* > 1 for slow motion (2 = half speed, with real in-between frames).
    Returns (file, engine used: "rife" or "minterpolate")."""
    exe = ffmpeg()
    has_audio, length = probe(src)
    out = out or src.with_name(f"{src.stem}-{fps}fps{'-lento' if slow > 1 else ''}.mp4")
    rife = find_rife() if engine in ("auto", "rife") else None
    if rife is None:
        if engine == "rife":
            raise RuntimeError("RIFE no está instalado (diga «instala RIFE»).")
        vf = (f"setpts={slow}*PTS," if slow > 1 else "") + minterpolate_filter(fps)
        sound = ["-c:a", "aac"] if has_audio and slow <= 1 else ["-an"]  # slow motion drops the sound
        cmd = [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vf", vf, *sound,
               "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", *REC709, str(out)]
        done = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise RuntimeError("La interpolación falló: " + done.stderr[-300:])
        return out, "minterpolate"
    with tempfile.TemporaryDirectory(prefix="sergio-rife-") as tmp:
        frames_in, frames_out = Path(tmp) / "in", Path(tmp) / "out"
        frames_in.mkdir()
        frames_out.mkdir()
        subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vsync", "0",
                        str(frames_in / "%08d.png")], check=True)
        count = len(list(frames_in.glob("*.png")))
        src_fps = count / max(length, 0.01)
        factor = max(2, round(fps * slow / max(src_fps, 1)))
        done = subprocess.run(rife_command(rife, frames_in, frames_out, count * factor, gpu), capture_output=True,
                              text=True, cwd=rife.parent, check=False)
        if done.returncode != 0 or not any(frames_out.iterdir()):
            raise RuntimeError("RIFE falló: " + (done.stderr or done.stdout)[-300:])
        rate = src_fps * factor / slow  # slow motion plays the extra frames at the source pace
        cmd = [exe, "-y", "-hide_banner", "-loglevel", "error", "-framerate", f"{rate:.4f}", "-i",
               str(frames_out / "%08d.png")]
        if has_audio and slow <= 1:
            cmd += ["-i", str(src), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-shortest"]
        cmd += ["-r", str(fps), "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", *REC709, str(out)]
        subprocess.run(cmd, check=True, capture_output=True)
    return out, "rife"


# -- silences (auto-editor) -----------------------------------------------------------
def find_auto_editor() -> str:
    found = shutil.which("auto-editor")
    if found:
        return found
    import sys

    scripts = Path(sys.executable).parent
    for name in ("auto-editor.exe", "auto-editor"):
        if (scripts / name).exists():
            return str(scripts / name)
    raise RuntimeError("Falta auto-editor (lo instala «sergio escritorio instalar»).")


def auto_editor_command(src: Path, out: Path, threshold: float = 0.04, margin: float = 0.2, exe: str = "auto-editor") -> list[str]:
    return [exe, str(src), "--edit", f"audio:threshold={threshold:g}", "--margin", f"{margin:g}sec",
            "-o", str(out), "--no-open", "--progress", "none"]


def cut_silences(src: Path, out: Path | None = None, threshold: float = 0.04, margin: float = 0.2) -> Path:
    """The clip without its silences (auto-editor), cuts padded by *margin*."""
    out = out or src.with_name(f"{src.stem}-sin-silencios{src.suffix}")
    done = subprocess.run(auto_editor_command(src, out, threshold, margin, find_auto_editor()), capture_output=True,
                          text=True, check=False)
    if done.returncode != 0 or not out.exists():
        raise RuntimeError("auto-editor falló: " + (done.stderr or done.stdout)[-300:])
    return out


# -- photos as clips (MoviePy) ----------------------------------------------------------
PHOTO = (".jpg", ".jpeg", ".png", ".webp", ".heic")


def ken_burns(image: Path, out: Path, seconds: float = 4.0, size: tuple[int, int] = (1920, 1080), zoom: float = 1.12) -> Path:
    """A photo as a clip with a slow push-in: MoviePy if installed, else ffmpeg."""
    w, h = size
    try:
        from moviepy import ImageClip

        clip = ImageClip(str(image)).with_duration(seconds)
        scale = max(w / clip.w, h / clip.h)
        clip = clip.resized(lambda t: scale * (1 + (zoom - 1) * t / seconds)).with_position("center")
        from moviepy import CompositeVideoClip

        CompositeVideoClip([clip], size=size).with_duration(seconds).write_videofile(
            str(out), fps=30, codec="libx264", audio=False, logger=None, preset="medium",
            ffmpeg_params=["-pix_fmt", "yuv420p"])
        return out
    except ImportError:
        frames = int(seconds * 30)
        vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
              f"zoompan=z='1+{zoom - 1:.3f}*on/{frames}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":s={w}x{h}:fps=30,format=yuv420p")
        subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(image), "-vf", vf,
                        "-frames:v", str(frames), "-c:v", "libx264", str(out)], check=True)
        return out


# -- the whole job ------------------------------------------------------------------------
def options_from(request: str) -> dict[str, Any]:
    """What the order asks for, besides the cut itself."""
    import unicodedata

    t = "".join(c for c in unicodedata.normalize("NFKD", request.lower()) if not unicodedata.combining(c))
    opts: dict[str, Any] = {}
    if re.search(r"\b(silencio|silencios|pausas|tiempos muertos)\b", t):
        opts["silences"] = True
    found = re.search(r"\b(\d{2,3})\s*(fps|cuadros|fotogramas)\b", t)
    if found:
        opts["fps"] = int(found.group(1))
    if re.search(r"\b(camara lenta|slow ?motion|a camara lenta|ralenti)\b", t):
        opts["slow"] = 2.0
        opts.setdefault("fps", 60)
    if re.search(r"\binterpol", t):
        opts.setdefault("fps", 60)
    if re.search(r"\b(dnxhr|avid)\b", t):
        opts["master"] = "dnxhr"
    elif re.search(r"\b(4444|con alfa|transparencia)\b", t):
        opts["master"] = "prores4444"
    elif re.search(r"\b(prores|master|maste?r|posproduccion|10 ?bits|davinci|premiere|final cut)\b", t):
        opts["master"] = "prores"
    elif re.search(r"\b(hevc|h\.?265)\b", t):
        opts["master"] = "hevc10"
    if re.search(r"\b(lut|look de cine|cinematografic\w*)\b", t):
        opts["contrast_curve"] = True
    if re.search(r"\b(limpia el ruido|quita el ruido|reduce el ruido|denoise|grano)\b", t):
        opts["denoise"] = True
    if re.search(r"\b(nitid\w*|enfoca\w*|sharpen)\b", t):
        opts["sharpen"] = True
    return opts


def prepare_sources(folder: Path, clips: list[Path], *, silences: bool, log: Callable[[str], None]) -> list[Path]:
    """Before planning: photos -> clips, talking clips -> without silences."""
    out: list[Path] = []
    work = folder / ".sergio"
    work.mkdir(exist_ok=True)
    for clip in clips:
        if clip.suffix.lower() in PHOTO:
            made = ken_burns(clip, work / f"{clip.stem}-foto.mp4")
            log(f"foto {clip.name} -> clip de 4 s con acercamiento")
            out.append(made)
        elif silences:
            try:
                made = cut_silences(clip, work / f"{clip.stem}-sin-silencios.mp4")
                log(f"silencios quitados de {clip.name}")
                out.append(made)
            except RuntimeError as exc:
                log(f"{clip.name}: {exc}")
                out.append(clip)
        else:
            out.append(clip)
    return out


def finish(video: Path, opts: dict[str, Any], *, grade: str = "", log: Callable[[str], None]) -> dict[str, Any]:
    """After the cut: interpolation, then the master with the colour chain."""
    result: dict[str, Any] = {"delivery": str(video)}
    if opts.get("fps") or opts.get("slow"):
        smooth, engine = interpolate(video, fps=int(opts.get("fps") or 60), slow=float(opts.get("slow") or 1.0))
        log(f"interpolación {engine}: {smooth.name}")
        result["interpolated"] = str(smooth)
        result["engine"] = engine
        video = smooth
    if opts.get("master"):
        chain = color_chain(lut=opts.get("lut", ""), denoise=bool(opts.get("denoise")), sharpen=bool(opts.get("sharpen")),
                            contrast_curve=bool(opts.get("contrast_curve")), grade=grade)
        made = master(video, opts["master"], color=chain)
        log(f"máster {MASTERS[opts['master']]['label']}: {made.name}")
        result["master"] = str(made)
        result["master_label"] = MASTERS[opts["master"]]["label"]
    return result


__all__ = [
    "MASTERS", "color_chain", "cut_silences", "finish", "install_rife", "interpolate", "ken_burns",
    "master_command", "options_from", "prepare_sources",
]
