"""The concierge as one tool: ``conserje`` (``openjarvis/conserje/``).

Everything is prepared to the last step; buying, paying, booking, publishing,
sending and unlocking wait for the owner's yes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

ACTIONS = [
    "restaurante",
    "vuelos",
    "hotel",
    "viaje",
    "transporte",
    "comida",
    "descuentos",
    "vender",
    "responder_comprador",
    "tesla",
    "hoy",
    "correos_masivos",
    "historia_instagram",
]


def _screen(goal: str) -> str:
    """Do it on the owner's screen with his sessions; stops before the last step."""
    try:
        from openjarvis.tools.desktop_tools import DesktopActionTool

        res = DesktopActionTool().execute(
            action="operate", target=goal, confirmed=False
        )
        return res.content or ""
    except Exception as exc:  # noqa: BLE001 — no desktop: the links still work
        return f"No pude usar su pantalla ({str(exc)[:120]}); use los enlaces."


@ToolRegistry.register("conserje")
class ConciergeTool(BaseTool):
    """Reservations, flights, trips, rides, food, selling, the car, the day."""

    tool_id = "conserje"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="conserje",
            description=(
                "The owner's personal concierge, like the best executive assistant. "
                "action: 'restaurante' (book a table, also hard-to-get ones: when its "
                "book opens, reminder, official waitlist, phone script) · 'vuelos' "
                "(real flight prices) · 'hotel' · 'viaje' (a whole trip to a budget: "
                "split, flights, hotels, day-by-day plan, documents) · 'transporte' "
                "(Uber/taxi) · 'comida' (delivery) · 'descuentos' · 'vender' (find the "
                "item's photos in his gallery, cut out the background, write the ad from "
                "his facts, put it on Facebook Marketplace / eBay / Mercado Libre) · "
                "'responder_comprador' (draft a reply to a buyer) · 'tesla' (climate, "
                "lock, honk, battery; moving the car is not possible by API) · 'hoy' "
                "(his day: calendar, reminders, trips) · 'correos_masivos' (one personal "
                "DRAFT per contact from a CSV; never sent) · 'historia_instagram'. "
                "'en_pantalla': true fills the real page on his PC with his own session "
                "and stops before paying, booking or publishing. Buying, paying, booking, "
                "publishing, sending and unlocking always wait for his yes."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ACTIONS},
                    "que": {
                        "type": "string",
                        "description": "restaurant, item, food, order for the car, "
                        "destination or buyer message",
                    },
                    "ciudad": {"type": "string"},
                    "origen": {"type": "string"},
                    "destino": {"type": "string"},
                    "fecha": {"type": "string", "description": "YYYY-MM-DD"},
                    "regreso": {"type": "string", "description": "YYYY-MM-DD"},
                    "hora": {"type": "string"},
                    "personas": {"type": "integer"},
                    "dias": {"type": "integer"},
                    "presupuesto": {"type": "number"},
                    "moneda": {"type": "string"},
                    "intereses": {"type": "string"},
                    "detalles": {
                        "type": "string",
                        "description": "vender: model, storage, state, what comes "
                        "with it (only what he said)",
                    },
                    "precio": {"type": "string"},
                    "plataformas": {"type": "array", "items": {"type": "string"}},
                    "pais": {"type": "string"},
                    "archivo": {
                        "type": "string",
                        "description": "CSV of contacts (correos_masivos) or the "
                        "photo/video (historia_instagram)",
                    },
                    "asunto": {"type": "string"},
                    "plantilla": {
                        "type": "string",
                        "description": "mail text with {nombre}, {empresa}…",
                    },
                    "en_pantalla": {"type": "boolean"},
                },
                "required": ["action"],
            },
            category="assistant",
            timeout_seconds=900,
        )

    def execute(self, **p: Any) -> ToolResult:
        action = str(p.get("action") or "")
        try:
            text = getattr(self, f"_{action}")(p)
        except AttributeError:
            return self._fail(f"No conozco la acción «{action}».")
        except Exception as exc:  # noqa: BLE001 — plain words, never a crash
            return self._fail(f"No pude hacerlo: {str(exc)[:240]}")
        return ToolResult(tool_name=self.tool_id, content=text, success=True)

    def _fail(self, text: str) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=text, success=False)

    # -- the actions --------------------------------------------------------------------

    def _restaurante(self, p: Dict[str, Any]) -> str:
        from openjarvis.conserje import enlaces, restaurantes

        r = restaurantes.plan(
            str(p.get("que") or ""),
            city=str(p.get("ciudad") or ""),
            date=str(p.get("fecha") or ""),
            time=str(p.get("hora") or ""),
            people=int(p.get("personas") or 2),
        )
        out = [f"Reserva en {r.restaurante}:", *[f"- {s}" for s in r.pasos]]
        saved = restaurantes.remind(r)
        if saved:
            out.append(saved)
        out += [
            "Enlaces:",
            enlaces.lines(r.enlaces),
            "Guion de la llamada:",
            r.guion_llamada,
        ]
        if p.get("en_pantalla"):
            out.append("En su pantalla: " + _screen(restaurantes.operator_goal(r)))
        return "\n".join(out)

    def _vuelos(self, p: Dict[str, Any]) -> str:
        from openjarvis.conserje import enlaces, viajes

        got = viajes.search_flights(
            str(p.get("origen") or ""),
            str(p.get("destino") or p.get("que") or ""),
            str(p.get("fecha") or ""),
            back=str(p.get("regreso") or ""),
            adults=int(p.get("personas") or 1),
        )
        offers = got.get("ofertas") or []
        if offers:
            head = "Vuelos con precio real (Duffel), del más barato:\n"
            body = "\n".join(f"- {o.line()}" for o in offers)
        else:
            head = (
                "Sin clave de Duffel (DUFFEL_ACCESS_TOKEN) no tengo precios en vivo. "
            )
            body = "Busque aquí, ya con su búsqueda puesta:"
        text = head + body + "\n" + enlaces.lines(got.get("enlaces") or {})
        text += "\nPagar el vuelo lo hace usted en la página (yo lo dejo listo)."
        if p.get("en_pantalla"):
            text += "\nEn su pantalla: " + _screen(
                f"Abre {next(iter((got.get('enlaces') or {'': ''}).values()))} y deja "
                "elegido el vuelo más barato que cumpla lo pedido. DETENTE antes de pagar; "
                "no escribas datos de tarjeta ni contraseñas."
            )
        return text

    def _hotel(self, p: Dict[str, Any]) -> str:
        from openjarvis.conserje import enlaces

        city = str(p.get("destino") or p.get("ciudad") or p.get("que") or "")
        links = enlaces.hotels(
            city, str(p.get("fecha") or ""), str(p.get("regreso") or ""),
            int(p.get("personas") or 2),
        )  # fmt: skip
        text = f"Hoteles en {city}:\n" + enlaces.lines(links)
        if p.get("en_pantalla"):
            budget = p.get("presupuesto")
            text += "\nEn su pantalla: " + _screen(
                f"Abre {links['Booking']}, filtra por cancelación gratis"
                + (f" y precio por noche hasta {budget}" if budget else "")
                + ", ordena por puntuación y deja elegida la mejor. DETENTE antes de "
                "reservar o pagar."
            )
        return text

    def _viaje(self, p: Dict[str, Any]) -> str:
        from openjarvis.conserje import enlaces, viajes

        t = viajes.plan_trip(
            str(p.get("destino") or p.get("que") or ""),
            days=int(p.get("dias") or 7),
            budget=float(p.get("presupuesto") or 0),
            currency=str(p.get("moneda") or "USD"),
            origin=str(p.get("origen") or ""),
            start=str(p.get("fecha") or ""),
            people=int(p.get("personas") or 1),
            interests=str(p.get("intereses") or ""),
        )
        out = [f"Viaje a {t.destino}, {t.dias} días, {t.personas} persona(s)."]
        if t.reparto:
            out.append("Presupuesto (reparto orientativo):")
            out += [f"- {k}: {v:,.2f} {t.moneda}" for k, v in t.reparto.items()]
        if t.vuelo_mas_barato:
            out.append("Vuelo más barato: " + t.vuelo_mas_barato)
        out.append("Itinerario:")
        for d in t.itinerario:
            bits = [d.get(k, "") for k in ("manana", "tarde", "noche") if d.get(k)]
            out.append(
                f"- Día {d.get('dia')}: {d.get('zona', '')}. " + " · ".join(bits)
            )
        for kind, links in t.enlaces.items():
            out += [f"{kind.capitalize()}:", enlaces.lines(links)]
        out += [
            "Documentos:",
            *[f"- {x}" for x in t.documentos],
            "Cómo seguimos:",
            *t.pasos,
        ]
        return "\n".join(out)

    def _transporte(self, p: Dict[str, Any]) -> str:
        from openjarvis.conserje import enlaces

        dest = str(p.get("destino") or p.get("que") or "")
        links = enlaces.rides(dest, str(p.get("origen") or ""))
        text = (
            f"Para ir a {dest}: el enlace de Uber abre la app con el destino puesto; "
            "usted toca «Confirmar».\n" + enlaces.lines(links)
        )
        if p.get("en_pantalla"):
            text += "\nEn su pantalla: " + _screen(
                f"Abre {links['Uber']} y deja el viaje a «{dest}» listo con la opción más "
                "cercana. DETENTE antes de «Confirmar» o «Solicitar»."
            )
        return text

    def _comida(self, p: Dict[str, Any]) -> str:
        from openjarvis.conserje import enlaces

        item = str(p.get("que") or "comida")
        links = enlaces.food(item, str(p.get("pais") or ""))
        text = f"«{item}» a domicilio:\n" + enlaces.lines(links)
        if p.get("en_pantalla"):
            first = next(iter(links.values()))
            budget = p.get("presupuesto")
            text += "\nEn su pantalla: " + _screen(
                f"Abre {first}, busca «{item}», elige la opción mejor puntuada que llegue "
                "antes"
                + (f" y cueste hasta {budget}" if budget else "")
                + ", agrégala al carrito y DETENTE antes de pagar o «Hacer pedido»."
            )
        return text

    def _descuentos(self, p: Dict[str, Any]) -> str:
        from openjarvis.conserje import enlaces

        item = str(p.get("que") or "")
        return (
            f"Dónde comparar y buscar cupones de «{item}»:\n"
            + enlaces.lines(enlaces.deals(item))
            + "\nComprar lo confirma usted."
        )

    def _vender(self, p: Dict[str, Any]) -> str:
        from openjarvis.conserje import venta

        ad = venta.listing(
            str(p.get("que") or ""),
            str(p.get("detalles") or ""),
            price=str(p.get("precio") or ""),
            platforms=[str(x) for x in (p.get("plataformas") or [])] or None,
        )
        photos = (
            f"{len(ad.fotos)} fotos suyas"
            + (
                ""
                if ad.fotos_comprobadas
                else " (por nombre, sin comprobar con visión)"
            )
            + f", {len(ad.recortes)} con fondo blanco"
        )
        out = [
            f"Anuncio listo: «{ad.titulo}»",
            f"Precio: {ad.precio} ({ad.precio_fuente})",
            f"Fotos: {photos} — carpeta {ad.carpeta}",
            "Descripción:",
            ad.descripcion,
        ]
        if not ad.fotos:
            out.append(
                "No encontré fotos de eso en su galería: tómele 3 o 4 y lo rehago."
            )
        for plat in ad.plataformas:
            if plat.lower() == "ebay" and venta.ebay_ready():
                out.append(
                    "eBay: lo publico con la API oficial en cuanto usted diga sí."
                )
            elif p.get("en_pantalla"):
                out.append(f"{plat}: " + _screen(venta.operator_goal(ad, plat)))
            else:
                out.append(f"{plat}: listo para llenarlo en su pantalla (en_pantalla).")
        out.append("Publicar y responder a interesados: con su sí.")
        return "\n".join(out)

    def _responder_comprador(self, p: Dict[str, Any]) -> str:
        import json

        from openjarvis.conserje import venta

        ad: Dict[str, Any] = {}
        if p.get("archivo"):
            try:
                ad = json.loads(Path(str(p["archivo"])).read_text("utf-8"))
            except (OSError, ValueError):
                ad = {}
        if not ad:
            ad = {"titulo": str(p.get("detalles") or "artículo"),
                  "precio": str(p.get("precio") or "")}  # fmt: skip
        reply = venta.reply_draft(str(p.get("que") or ""), ad)
        return f"Borrador para el interesado (lo envío solo con su sí):\n{reply}"

    def _tesla(self, p: Dict[str, Any]) -> str:
        from openjarvis.conserje import tesla

        return tesla.do(str(p.get("que") or ""))

    def _hoy(self, p: Dict[str, Any]) -> str:
        from openjarvis.conserje import agenda

        return agenda.today()

    def _correos_masivos(self, p: Dict[str, Any]) -> str:
        import time

        from openjarvis.conserje import correo

        contacts = correo.read_contacts(str(p.get("archivo") or ""))
        folder = Path.home() / "Sergio" / "correos" / time.strftime("%Y%m%d-%H%M%S")
        got = correo.drafts(
            str(p.get("asunto") or "Hola {nombre}"),
            str(p.get("plantilla") or p.get("que") or ""),
            contacts,
            folder,
        )
        extra = (
            f" ({got['omitidos']} quedaron fuera: máximo {correo.MAX})"
            if got["omitidos"]
            else ""
        )
        return (
            f"{got['borradores']} borradores personalizados en {got['carpeta']}{extra}. "
            "Cada uno lleva una línea para dejar de recibirlos. No envié ninguno: se "
            "abren con doble clic y se envían desde su correo."
        )

    def _historia_instagram(self, p: Dict[str, Any]) -> str:
        from openjarvis.automatiza import canales
        from openjarvis.conserje.aprobar import owner_yes

        media = Path(str(p.get("archivo") or "")).expanduser()
        if not media.is_file():
            return "Dígame qué foto o video subir (la ruta en su PC)."
        if not owner_yes(
            f"Subir a su historia de Instagram «{media.name}»", {"archivo": str(media)}
        ):
            return "No la subí: falta su sí."
        got = canales.instagram_story(media)
        return f"Historia publicada en su Instagram (id {got['historia']})."


__all__ = ["ACTIONS", "ConciergeTool"]
