"""«Pon a la venta mi iPhone»: photos, cut-outs, the listing, the platforms.

1. ``find_photos`` — the photos of THAT item in his gallery: the folders of
   pictures (and the phone's backup folders on the PC) are short-listed by
   name and date, then a vision model looks at each one («¿se ve un iPhone?»)
   and only the yes stay. Without a vision model: the name matches, marked
   «sin comprobar».
2. ``cutout`` — the item on a clean white background (``creator/segment``,
   U²-Net on this PC), the photo itself untouched beside it.
3. ``listing`` — title and description made **only from what he said**
   (model, storage, battery, state, what comes with it); nothing is invented.
   Price: his price, or the median of real sold/listed prices found, or «a
   definir» — never a made-up number.
4. Platforms: eBay by its official Sell API when its keys are in sergio.env,
   otherwise eBay, Facebook Marketplace and Mercado Libre are filled **on his
   screen** with his own session and stop before «Publicar».
5. ``reply_draft`` — the answer to an interested buyer, from the listing's
   facts only; what it does not know it asks him. Sending waits for his yes.

Photos from the internet are only used, if he asks, as «imagen de referencia»
next to his own photos: a used item is sold with photos of the real one.
"""

from __future__ import annotations

import json
import os
import re
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

Look = Callable[[bytes, str], str]
Ask = Callable[[str], str]
Search = Callable[[str], str]

MAX_LOOKS = 24


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "articulo").lower()).strip("-")
    return s[:40] or "articulo"


def _home() -> Path:
    base = os.environ.get("OPENJARVIS_HOME") or str(Path.home() / ".openjarvis")
    return Path(base) / "ventas"


def _default_look(image: bytes, question: str) -> str:
    from openjarvis.tools.vision_look import ask_image

    return ask_image(image, question, lite=True)


def _jpeg(path: Path, side: int = 768) -> bytes:
    """A small JPEG for the vision model (HEIC and PNG too, when Pillow can)."""
    from io import BytesIO

    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((side, side))
        buf = BytesIO()
        im.save(buf, "JPEG", quality=82)
        return buf.getvalue()


def find_photos(
    item: str,
    *,
    candidates: Optional[List[str]] = None,
    look: Optional[Look] = None,
    limit: int = 8,
) -> Dict[str, Any]:
    """``{"fotos": [...], "comprobadas": bool}``: photos that show *item*."""
    if candidates is None:
        from openjarvis.tools.commerce_intel import find_gallery_photos

        candidates = find_gallery_photos(item, max_photos=MAX_LOOKS * 2)
    look = look or _default_look
    question = (
        f"¿En esta foto se ve claramente un {item} (el objeto mismo, no una captura "
        "de pantalla ni un anuncio)? Responde solo «sí» o «no»."
    )
    from concurrent.futures import ThreadPoolExecutor

    def seen(path: str) -> Optional[bool]:
        try:
            answer = look(_jpeg(Path(path)), question)
        except Exception:  # noqa: BLE001 — no vision model for this one
            return None
        return bool(re.match(r"\s*(s[ií]|yes)\b", (answer or "").lower()))

    # four looks at a time (the order of the gallery is kept)
    with ThreadPoolExecutor(max_workers=4) as pool:
        verdicts = list(pool.map(seen, candidates[:MAX_LOOKS]))
    checked = any(v is not None for v in verdicts)
    yes = [p for p, v in zip(candidates[:MAX_LOOKS], verdicts) if v][:limit]
    if checked:
        return {"fotos": yes, "comprobadas": True}
    words = [w for w in re.findall(r"[a-z0-9]+", item.lower()) if len(w) > 2]
    named = [p for p in candidates if any(w in Path(p).name.lower() for w in words)]
    return {"fotos": named[:limit], "comprobadas": False}


def cutout(photo: str, out_dir: Path) -> str:
    """The item on white (PNG) next to the original; returns the new path."""
    import cv2
    import numpy as np

    from openjarvis.creator import segment

    img = cv2.imread(photo, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"No pude abrir {photo}")
    a = segment.alpha(img)[..., None]
    white = np.full_like(img, 255)
    out = (img * a + white * (1 - a)).astype("uint8")
    ys, xs = np.where(a[..., 0] > 0.5)
    if ys.size:
        pad = 24
        y0, y1 = max(0, ys.min() - pad), min(img.shape[0], ys.max() + pad)
        x0, x1 = max(0, xs.min() - pad), min(img.shape[1], xs.max() + pad)
        out = out[y0:y1, x0:x1]
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{Path(photo).stem}_fondo_blanco.png"
    cv2.imwrite(str(dest), out)
    return str(dest)


@dataclass
class Listing:
    articulo: str
    titulo: str
    descripcion: str
    precio: str
    precio_fuente: str
    fotos: List[str] = field(default_factory=list)
    recortes: List[str] = field(default_factory=list)
    plataformas: List[str] = field(default_factory=list)
    carpeta: str = ""
    fotos_comprobadas: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def price_from_market(item: str, search: Optional[Search] = None) -> Dict[str, str]:
    """The median of real prices found for the same item, or nothing."""
    try:
        if search is None:
            from openjarvis.tools.web_search import WebSearchTool

            text = (
                WebSearchTool(max_results=8)
                .execute(query=f"{item} usado precio vendido ebay mercado libre")
                .content
                or ""
            )
        else:
            text = search(item)
    except Exception:  # noqa: BLE001
        return {}
    prices = []
    for m in re.finditer(r"(?:US\$|\$|USD\s?)\s?(\d{2,5}(?:[.,]\d{2})?)", text):
        try:
            prices.append(float(m.group(1).replace(",", ".")))
        except ValueError:
            continue
    prices = [p for p in prices if 10 <= p <= 20000]
    if len(prices) < 3:
        return {}
    med = statistics.median(prices)
    return {
        "precio": f"{round(med / 5) * 5:g} USD",
        "fuente": f"mediana de {len(prices)} precios reales encontrados en la web",
    }


def listing(
    item: str,
    facts: str = "",
    *,
    price: str = "",
    platforms: Optional[List[str]] = None,
    photos: Optional[List[str]] = None,
    ask: Optional[Ask] = None,
    search: Optional[Search] = None,
    root: Optional[Path] = None,
    make_cutouts: bool = True,
) -> Listing:
    """The ad, ready to publish (publishing waits for his yes)."""
    if not item.strip():
        raise ValueError("Dígame qué quiere vender.")
    folder = (root or _home()) / _slug(item)
    folder.mkdir(parents=True, exist_ok=True)
    if price.strip():
        chosen, source = price.strip(), "su precio"
    else:
        found = price_from_market(item, search)
        chosen = found.get("precio", "a definir")
        source = found.get(
            "fuente", "no encontré precios reales suficientes; dígame uno"
        )
    title, desc = _write(item, facts, ask)
    ad = Listing(item.strip(), title, desc, chosen, source,
                 plataformas=platforms or ["Facebook Marketplace", "eBay"],
                 carpeta=str(folder))  # fmt: skip
    if photos is None:
        got = find_photos(item)
        photos, ad.fotos_comprobadas = got["fotos"], got["comprobadas"]
    ad.fotos = list(photos)
    if make_cutouts:
        for p in ad.fotos[:6]:
            try:
                ad.recortes.append(cutout(p, folder))
            except Exception:  # noqa: BLE001 — keep the original photo
                continue
    (folder / "anuncio.json").write_text(
        json.dumps(ad.to_dict(), ensure_ascii=False, indent=2), "utf-8"
    )
    return ad


def _write(item: str, facts: str, ask: Optional[Ask]) -> tuple:
    plain_title = f"{item.strip()}"[:80]
    plain_desc = (facts.strip() or "Detalles a confirmar con el vendedor.") + (
        "\nEntrega en mano o envío a convenir."
    )
    prompt = (
        "Write a second-hand marketplace ad in Spanish. Use ONLY these facts; do "
        "not add condition, accessories, warranty or anything not written here. "
        f"Item: {item}. Facts: {facts or 'none given'}. Answer only JSON: "
        '{"titulo": "max 80 characters", "descripcion": "short, clear, honest"}'
    )
    try:
        if ask is None:
            from openjarvis.creator.llm import ask as ask_model

            raw = ask_model(prompt)
        else:
            raw = ask(prompt)
        m = re.search(r"\{.*\}", raw or "", re.S)
        data = json.loads(m.group(0)) if m else {}
        title = str(data.get("titulo") or plain_title)[:80]
        desc = str(data.get("descripcion") or plain_desc)[:2000]
        return title, desc
    except Exception:  # noqa: BLE001 — the plain ad
        return plain_title, plain_desc


SELL_PAGES = {
    "facebook marketplace": "https://www.facebook.com/marketplace/create/item",
    "ebay": "https://www.ebay.com/sl/sell",
    "mercado libre": "https://www.mercadolibre.com/jms/vender",
}


def operator_goal(ad: Listing, platform: str) -> str:
    """What the screen operator does on his PC; it stops before «Publicar»."""
    url = SELL_PAGES.get(platform.lower(), SELL_PAGES["facebook marketplace"])
    pics = ad.recortes or ad.fotos
    return (
        f"Abre {url} con la sesión del señor. Crea un anuncio: título «{ad.titulo}», "
        f"precio {ad.precio}, descripción «{ad.descripcion[:600]}». Sube estas fotos "
        f"desde la carpeta {ad.carpeta}: {', '.join(Path(p).name for p in pics[:10])}. "
        "Elige la categoría y el estado que correspondan a la descripción. DETENTE antes "
        "de «Publicar»: lo publica el señor. No escribas contraseñas."
    )


def ebay_ready() -> bool:
    need = ("EBAY_USER_TOKEN", "EBAY_FULFILLMENT_POLICY", "EBAY_PAYMENT_POLICY",
            "EBAY_RETURN_POLICY", "EBAY_LOCATION_KEY", "EBAY_CATEGORY_ID")  # fmt: skip
    return all(os.environ.get(k, "").strip() for k in need)


def ebay_publish(ad: Listing, image_urls: List[str], *, http: Any = None,
                 approver: Any = None) -> Dict[str, str]:  # fmt: skip
    """eBay Sell Inventory API: item, offer, publish — after his yes."""
    from openjarvis.conserje.aprobar import owner_yes

    if not ebay_ready():
        raise RuntimeError("Faltan las claves de eBay en sergio.env.")
    num = re.search(r"\d+(?:\.\d+)?", ad.precio or "")
    if not num:
        raise RuntimeError("El anuncio no tiene precio: dígame uno.")
    if not owner_yes(f"Publicar en eBay «{ad.titulo}» por {ad.precio}",
                     {"anuncio": ad.to_dict()}, approver=approver):  # fmt: skip
        return {"estado": "no publicado (sin su sí)"}
    import httpx

    http = http or httpx.Client(timeout=40)
    env = os.environ
    base = "https://api.ebay.com/sell/inventory/v1"
    h = {"Authorization": f"Bearer {env['EBAY_USER_TOKEN']}",
         "Content-Type": "application/json", "Content-Language": "es-US"}  # fmt: skip
    sku = f"sergio-{_slug(ad.titulo)}"
    r = http.put(f"{base}/inventory_item/{sku}", headers=h, json={
        "availability": {"shipToLocationAvailability": {"quantity": 1}},
        "condition": "USED_EXCELLENT" if "excelente" in ad.descripcion.lower() else "USED_GOOD",
        "product": {"title": ad.titulo, "description": ad.descripcion,
                    "imageUrls": image_urls[:12]},
    })  # fmt: skip
    r.raise_for_status()
    r = http.post(f"{base}/offer", headers=h, json={
        "sku": sku, "marketplaceId": env.get("EBAY_MARKETPLACE", "EBAY_US"),
        "format": "FIXED_PRICE", "availableQuantity": 1,
        "categoryId": env["EBAY_CATEGORY_ID"], "listingDescription": ad.descripcion,
        "merchantLocationKey": env["EBAY_LOCATION_KEY"],
        "listingPolicies": {"fulfillmentPolicyId": env["EBAY_FULFILLMENT_POLICY"],
                            "paymentPolicyId": env["EBAY_PAYMENT_POLICY"],
                            "returnPolicyId": env["EBAY_RETURN_POLICY"]},
        "pricingSummary": {"price": {"value": num.group(0), "currency": "USD"}},
    })  # fmt: skip
    r.raise_for_status()
    offer = (r.json() or {}).get("offerId", "")
    r = http.post(f"{base}/offer/{offer}/publish", headers=h)
    r.raise_for_status()
    return {
        "estado": "publicado",
        "listingId": str((r.json() or {}).get("listingId", "")),
    }


def reply_draft(message: str, ad: Dict[str, Any], *, ask: Optional[Ask] = None) -> str:
    """A reply to a buyer from the ad's facts only (sending waits for his yes)."""
    facts = json.dumps({k: ad.get(k) for k in ("titulo", "descripcion", "precio")},
                       ensure_ascii=False)  # fmt: skip
    prompt = (
        "You answer a buyer for the owner. Spanish, short, polite. Use ONLY these "
        f"facts: {facts}. If the buyer asks something not in the facts, say you will "
        "check and answer soon. Never accept a price below the listed one without "
        "saying you will ask the owner. Never share addresses or phone numbers. "
        f"Buyer: {message}\nReply:"
    )
    try:
        if ask is None:
            from openjarvis.creator.llm import ask as ask_model

            out = ask_model(prompt)
        else:
            out = ask(prompt)
        if out and out.strip():
            return out.strip()[:800]
    except Exception:  # noqa: BLE001
        pass
    return (
        f"¡Hola! Gracias por escribir. El {ad.get('titulo', 'artículo')} está en "
        f"{ad.get('precio', 'precio a confirmar')}. Le confirmo el resto en un momento."
    )


__all__ = [
    "Listing",
    "cutout",
    "ebay_publish",
    "ebay_ready",
    "find_photos",
    "listing",
    "operator_goal",
    "price_from_market",
    "reply_draft",
]
