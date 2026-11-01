"""Owner, 29 Oct 2026: «le dije que entre a Amazon, inicie sesión y busque
unos productos y me dijo que es un modelo de lenguaje… necesitamos control
total y cualquier tarea; la conversación por voz a veces no se termina; no
puede hacer split screen»."""

import json
import time

from sergio_escritorio import launch
from sergio_escritorio.apps import Launcher, Window
from sergio_escritorio.call import QUIET_TURNS, is_goodbye
from sergio_escritorio.control import Controller, halves, risky, split_targets
from sergio_escritorio.quick import parse_quick

from tests.escritorio.test_call import FakeLine, _call, _wait

# -- split screen: two programs side by side --------------------------------------


def test_two_programs_go_side_by_side_by_voice():
    q = parse_quick("Sergio, pon Chrome y Word lado a lado")
    assert q.kind == "split_apps" and q.arg == "chrome | word"
    assert parse_quick("divide la pantalla entre excel y teams").arg == "excel | teams"
    assert (
        parse_quick("pon spotify con chrome en pantalla dividida").kind == "split_apps"
    )
    # without names it still splits Sergio's own window (and says so)
    alone = parse_quick("divide la pantalla")
    assert alone.kind == "multitask_on" and "pantalla" in alone.say


def test_split_targets_and_the_two_halves():
    assert split_targets("Chrome | Word") == ("Chrome", "Word")
    assert split_targets("chrome y word") == ("chrome", "word")
    assert split_targets("Excel") == ("Excel", "")
    assert split_targets("") == ("", "")
    left, right = halves((0, 0, 1921, 1040))
    assert left == (0, 0, 960, 1040) and right == (960, 0, 961, 1040)
    assert halves((1920, 0, 3840, 1080))[0][0] == 1920  # the second monitor


def test_split_is_an_ordinary_move_that_never_asks(desktop):
    placed = []
    desktop.side_by_side = lambda a, b: placed.append((a, b)) or [a, b]
    asked = []
    c = Controller(
        desktop, sleep=lambda s: None, approve=lambda p: asked.append(p) or True
    )
    assert not risky({"action": "split", "target": "Chrome | Word"})
    assert "split screen: Chrome | Word" in c.act(
        {"action": "split", "target": "Chrome | Word"}
    )
    assert placed == [("Chrome", "Word")] and asked == []


def test_the_launcher_finds_an_open_program_by_its_program_first():
    class Desk:
        def windows(self):
            return [
                Window(1, "cómo usar Word - Google Chrome", "chrome"),
                Window(2, "Documento1 - Word", "winword"),
                Window(3, "Sergio", "msedge"),
            ]

    launcher = Launcher(desktop=Desk(), rescan=lambda: None)
    launcher._scanned = True
    assert launcher.window("word").hwnd == 2
    assert launcher.window("chrome").hwnd == 1
    assert launcher.window("chrome", skip=1) is None
    assert launcher.window("sergio") is None  # never its own window


def test_splitting_with_no_sergio_window_open_opens_one_already_split():
    class No:
        status_code = 503

        def json(self):
            return {}

    opened = []
    assert launch.split_window(True, post=lambda *a, **k: No(), opener=opened.append)
    assert opened and opened[0].endswith("/?dividir=1")
    assert not launch.split_window(
        False, post=lambda *a, **k: No(), opener=opened.append
    )
    assert len(opened) == 1  # joining never opens a window


# -- the voice conversation ends --------------------------------------------------


def test_a_short_goodbye_is_a_goodbye_and_a_sentence_with_the_word_is_not():
    for bye in (
        "gracias, adiós",
        "cuelga",
        "eso es todo",
        "chao Sergio",
        "hasta mañana",
    ):
        assert is_goodbye(bye), bye
    for not_bye in (
        "",
        "busca la canción Adiós de Gustavo Cerati en Spotify y ponla bien alta",
        "abre Chrome",
    ):
        assert not is_goodbye(not_bye), not_bye


def test_saying_goodbye_hangs_up_even_if_the_model_does_not():
    ended = []
    line = FakeLine([json.dumps({"type": "ready", "model": "m"})])
    call = _call(line, on_end=ended.append, idle_hang_up=float("inf"))
    assert call.start()
    line.inbox.put(json.dumps({"type": "heard", "text": "gracias Sergio, adiós"}))
    line.inbox.put(json.dumps({"type": "said", "text": "A sus órdenes, señor."}))
    line.inbox.put(json.dumps({"type": "turn_complete"}))
    assert _wait(lambda: not call.active, 5)
    assert ended == ["te despediste"]


def test_an_always_on_call_ends_after_ten_minutes_without_a_real_exchange():
    now = [100.0]
    ended = []
    line = FakeLine([json.dumps({"type": "ready", "model": "m"})])
    call = _call(
        line, clock=lambda: now[0], idle_hang_up=float("inf"), on_end=ended.append
    )
    assert call.start()
    now[0] += QUIET_TURNS - 5
    time.sleep(0.3)
    assert call.active  # always-on: silence alone never ends it
    now[0] += 10
    assert _wait(lambda: not call.active)
    assert ended == ["sin conversación"]


def test_everyday_orders_route_to_agent_and_activate_neurons():
    from openjarvis.connectome import neurons
    from sergio_escritorio.voice import needs_agent

    orders = (
        "pídeme una pizza por Uber Eats",
        "pide un Uber al aeropuerto",
        "haz las compras del supermercado por internet",
        "pide ropa por internet en Zara y agrégala a mi carrito",
        "encuentra unos audífonos Sony en Amazon y agrégalos a mi carrito",
        "vende mi teléfono iPhone 15 Pro en muchas plataformas con título y todo",
        "escribe un correo a cliente@empresa.com con la propuesta comercial",
        "ponme un recordatorio en 30 minutos para llamar al banco",
    )
    for phrase in orders:
        assert needs_agent(phrase), f"needs_agent failed for: {phrase}"
        sel = neurons.select(neurons.normalise(phrase), {})
        assert sel is not None, f"neurons.select returned None for: {phrase}"
        assert "sergio_app" in sel.tools
        assert ("desktop_action" in sel.tools) or ("reminders" in sel.tools), phrase


def test_sergio_app_executes_delivery_shopping_selling_email_and_reminders(monkeypatch, tmp_path):
    from openjarvis.core.types import ToolResult
    from openjarvis.tools.app_control import SergioAppControlTool
    from openjarvis.tools.desktop_tools import DesktopActionTool

    recorded = []

    def fake_execute(self, **params):
        recorded.append(params)
        return ToolResult(tool_name="desktop_action", content=" ejecutado en pantalla", success=True)

    monkeypatch.setattr(DesktopActionTool, "execute", fake_execute)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    tool = SergioAppControlTool()

    r1 = tool.execute(action="delivery_order", platform="ubereats", content="Hamburguesa doble", to="Casa")
    assert r1.success and "Uber" in r1.content
    assert any(c.get("action") == "operate" and c.get("confirmed") is True for c in recorded)

    recorded.clear()
    r2 = tool.execute(action="shop_cart", platform="amazon", content="Chaqueta negra talla M")
    assert r2.success and "Amazon" in r2.content
    assert any(c.get("action") == "operate" and "carrito" in c.get("target", "") for c in recorded)

    recorded.clear()
    r3 = tool.execute(
        action="sell_multiplatform",
        title="iPhone 15 Pro 256GB Titanio",
        price="850 USD",
        content="Batería al 94%, caja original y cable USB-C.",
        platform="marketplace,mercadolibre,ebay",
    )
    assert r3.success and "iPhone 15 Pro 256GB Titanio" in r3.content and "850 USD" in r3.content
    open_calls = [c for c in recorded if c.get("action") == "open"]
    assert len(open_calls) == 3

    recorded.clear()
    r4 = tool.execute(
        action="send_email",
        platform="gmail",
        to="socio@empresa.com",
        title="Contrato listo",
        content="Adjunto los términos finales.",
    )
    assert r4.success and "socio@empresa.com" in r4.content
    assert recorded[-1]["action"] == "message" and recorded[-1]["confirmed"] is True


def test_faster_operator_zero_lag_subtitles_and_video_trend_skills(monkeypatch):
    from openjarvis.tools.app_control import SergioAppControlTool
    from sergio_escritorio import operador, video_pro

    # 1. Operator settle times are fast and responsive
    assert operador.SETTLE["click"] <= 0.35
    assert operador.SETTLE["type"] <= 0.15
    assert operador.SETTLE["open"] <= 0.9

    # 2. Kinetic captions in video_pro weight longer words proportionally with zero start lag
    filt = video_pro.caption_filter(
        "Sí extraordinariamente",
        3.0,
        1080,
        {"kinetic": True, "style": "caps"},
    )
    assert "between(t,0.00," in filt

    # 3. sergio_app video_create (Zack D. Films & MrBeast), find_clips, niche_trends, pc_control
    tool = SergioAppControlTool()
    monkeypatch.setattr(
        "openjarvis.video_essay.job.start",
        lambda params: {"id": "job_test_1", "params": params},
    )
    v_zack = tool.execute(
        action="video_create",
        platform="zack d films",
        content="Cómo funciona el corazón humano por dentro en 3D",
    )
    assert v_zack.success and "explicado3d" in v_zack.content

    v_beast = tool.execute(
        action="video_create",
        platform="mrbeast",
        content="Sobreviví 50 horas en una isla desierta",
    )
    assert v_beast.success and "pesada" in v_beast.content

    clips_res = tool.execute(action="find_clips", content="no rendirse entrenar subir escaleras")
    assert clips_res.success and "Rocky" in clips_res.content

    monkeypatch.setattr(
        "openjarvis.automatiza.tendencias.read",
        lambda country="EC", niche="": {
            "fuentes": ["Google Trends", "YouTube"],
            "senales": [{"tema": "IA en 3D", "fuente": "YouTube", "cifra": 500000}],
        },
    )
    monkeypatch.setattr(
        "openjarvis.video_essay.schedule.add",
        lambda idea, **kw: {"activo": True, "idea": idea, **kw},
    )
    trends_res = tool.execute(
        action="niche_trends",
        platform="EC",
        content="animación 3D",
        when="diario",
    )
    assert trends_res.success and "IA en 3D" in trends_res.content


def test_real_world_uber_food_budget_rare_item_and_gallery_selling(monkeypatch, tmp_path):
    from openjarvis.connectome import neurons
    from openjarvis.core.types import ToolResult
    from openjarvis.tools.app_control import SergioAppControlTool
    from openjarvis.tools.desktop_tools import DesktopActionTool, FaceApprovalTool

    recorded = []
    face_checks = []

    def fake_desktop_execute(self, **params):
        recorded.append(params)
        return ToolResult(tool_name="desktop_action", content=" ejecutado en pantalla", success=True)

    def fake_face_execute(self, **params):
        face_checks.append(params)
        return ToolResult(
            tool_name="face_approval",
            content="El señor aprobó en persona (rostro verificado 96 %, gesto «sí»).",
            success=True,
        )

    monkeypatch.setattr(DesktopActionTool, "execute", fake_desktop_execute)
    monkeypatch.setattr(FaceApprovalTool, "execute", fake_face_execute)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    # Also verify neuron selection for all 4 real-world voice sentences
    real_sentences = (
        "sergio pide un uber, quiero que me lleve de A a B en 5 minutos",
        "sergio pide 2 hamburguesas con french fries y soda, quiero que lleguen en 10 minutos maximo, solo tengo 10 usd",
        "sergio necesito encontrar este rare item Seiko SARB033, buscalo por un precio de mas o menos 450 usd con vendedores confiables",
        "sergio estoy planeando vender mi telefono, entra en mi galeria, busca fotos de el y publicalo en marketplace, ebay por un precio razonable y responde a quien escriba interesado",
    )
    for phrase in real_sentences:
        sel = neurons.select(neurons.normalise(phrase), {})
        assert sel is not None and "pantalla" in sel.neurons, phrase
        assert "sergio_app" in sel.tools and "face_approval" in sel.tools, phrase

    tool = SergioAppControlTool()

    # 1. Uber ride: A to B in 5 minutes using live location + Face ID
    r_uber = tool.execute(
        action="uber_ride",
        from_location="mi ubicacion",
        to="Aeropuerto Internacional",
        max_minutes=5,
    )
    assert r_uber.success
    assert "Aeropuerto Internacional" in r_uber.content
    assert "máximo 5 minutos" in r_uber.content
    assert "Confirmado con Face ID de Sergio" in r_uber.content
    assert any("m.uber.com" in str(c.get("target", "")) for c in recorded)

    # 2. Food delivery: 2 burgers + french fries + soda in <= 10 min and <= 10 USD + Face ID
    recorded.clear()
    r_food = tool.execute(
        action="delivery_order",
        platform="ubereats",
        content="2 hamburguesas con french fries y soda",
        budget="10 USD",
        max_minutes=10,
        to="Casa",
    )
    assert r_food.success
    assert "máximo 10 USD" in r_food.content
    assert "máximo 10 minutos" in r_food.content
    assert "Confirmado con Face ID de Sergio" in r_food.content
    assert any(
        c.get("action") == "operate"
        and "10 USD" in c.get("target", "")
        and "10 minutos" in c.get("target", "")
        for c in recorded
    )

    # 3. Rare item Deep Research: trusted sellers + target price + Face ID
    recorded.clear()
    r_rare = tool.execute(
        action="rare_item_search",
        content="Seiko SARB033 vintage watch",
        price="450 USD",
    )
    assert r_rare.success
    assert "Vendedores Confiables" in r_rare.content
    assert "450 USD" in r_rare.content
    assert "Confirmado con Face ID de Sergio" in r_rare.content

    # 4. Sell phone from Gallery + Fair Market Price + Auto-Reply to interested buyers
    recorded.clear()
    pics_dir = tmp_path / "Pictures"
    pics_dir.mkdir(parents=True, exist_ok=True)
    img1 = pics_dir / "iphone_15_pro_frontal.jpg"
    img2 = pics_dir / "iphone_15_pro_caja.png"
    img1.write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 12000)
    img2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 12000)

    r_sell = tool.execute(
        action="sell_multiplatform",
        title="iPhone 15 Pro",
        price="razonable",
        content="Impecable, único dueño, batería 95%",
        platform="marketplace,ebay",
        auto_reply=True,
    )
    assert r_sell.success
    assert "2 fotos encontradas en su galería" in r_sell.content
    assert "iphone_15_pro_frontal.jpg" in r_sell.content
    assert "740 USD" in r_sell.content
    assert "Autorespuesta a compradores interesados:** Activa en marketplace, ebay" in r_sell.content
    autoreply_file = tmp_path / "Sergio" / "ventas" / "autorespuestas_activas.json"
    assert autoreply_file.exists()
    assert len(face_checks) >= 4


def test_seven_top_lifestyle_concierge_categories_real_and_confirmed(monkeypatch, tmp_path):
    from openjarvis.connectome import neurons
    from openjarvis.core.types import ToolResult
    from openjarvis.tools.app_control import SergioAppControlTool
    from openjarvis.tools.desktop_tools import DesktopActionTool, FaceApprovalTool
    from sergio_escritorio.voice import needs_agent

    recorded = []
    face_checks = []

    def fake_desktop_execute(self, **params):
        recorded.append(params)
        return ToolResult(tool_name="desktop_action", content="ejecutado en pantalla", success=True)

    def fake_face_execute(self, **params):
        face_checks.append(params)
        return ToolResult(
            tool_name="face_approval",
            content="El señor aprobó en persona (rostro verificado 98 %).",
            success=True,
        )

    monkeypatch.setattr(DesktopActionTool, "execute", fake_desktop_execute)
    monkeypatch.setattr(FaceApprovalTool, "execute", fake_face_execute)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    tool = SergioAppControlTool()

    cases = [
        (
            "personal_shopping",
            "Necesito encontrar un Patek Philippe específico o un reloj con un calibre de micro-rotor de edición limitada, y que me lo entreguen en mi hotel antes de mañana.",
            "Chrono24",
            "Hotel",
            "antes de mañana",
        ),
        (
            "personal_shopping",
            "Consigue una chaqueta de Loro Piana de una colección pasada que está agotada a nivel mundial y envíala a mi casa en Cuenca.",
            "Farfetch",
            "Cuenca",
            "prioritario",
        ),
        (
            "dining_nightlife",
            "Reserva una mesa para dos esta noche en un restaurante de alta cocina que aplique técnicas de esferificación en su menú degustación, aunque el lugar tenga una lista de espera de seis meses.",
            "MICHELIN Guide",
            "Ciudad",
            "esta noche",
        ),
        (
            "travel_aviation",
            "Mi vuelo comercial se canceló. Necesito un jet privado listo en dos horas, un chofer esperando en la pista de aterrizaje y que mi suite habitual esté preparada.",
            "VistaJet",
            "Pista FBO / Suite",
            "en 2 horas",
        ),
        (
            "vip_events",
            "Quiero dos pases VIP con acceso a boxes y al paddock para la próxima competencia internacional de karts o motocross de este fin de semana.",
            "Paddock",
            "Circuito Internacional",
            "este fin de semana",
        ),
        (
            "lifestyle_gifting",
            "Mañana es el cumpleaños de una amiga cercana de la escuela. Necesito que compren un accesorio de diseñador, lo envuelvan impecablemente y lo entreguen en su colegio a primera hora, incluyendo una tarjeta escrita a mano.",
            "Farfetch",
            "Colegio",
            "mañana a primera hora",
        ),
        (
            "bespoke_advisory",
            "Quiero lanzar mi propia línea de perfumes de lujo con notas gourmand y mecanismos de empaque magnéticos personalizados; necesito que me contacten y agenden reuniones con las mejores casas perfumistas para iniciar el proyecto.",
            "Givaudan",
            "Grasse / Ginebra",
            "esta semana",
        ),
        (
            "emergency_security",
            "Perdí mi pasaporte mientras viajaba por Europa; necesito un reemplazo de emergencia tramitado hoy mismo y un abogado local bilingüe que me asista con el papeleo.",
            "Embajadas y Consulados",
            "Europa",
            "hoy mismo",
        ),
    ]

    for expected_cat, prompt, expected_portal, dest, when in cases:
        assert needs_agent(prompt), f"needs_agent failed for: {prompt}"
        sel = neurons.select(neurons.normalise(prompt), {})
        assert sel is not None and "pantalla" in sel.neurons, f"neuron failed for: {prompt}"
        assert "sergio_app" in sel.tools

        res = tool.execute(
            action="concierge_request",
            content=prompt,
            to=dest,
            when=when,
        )
        assert res.success, res.content
        assert expected_portal in res.content, f"Expected {expected_portal} in {res.content}"
        assert "Confirmado con Face ID de Sergio" in res.content
        assert "Recordatorio proactivo creado automáticamente" in res.content

    concierge_files = list((tmp_path / "Sergio" / "concierge").glob("orden_*.md"))
    assert len(concierge_files) == len(cases)
    proactive_file = tmp_path / "Sergio" / "recordatorios" / "recordatorios_proactivos.json"
    assert proactive_file.exists()


def test_multidevice_phone_video_meetings_academic_minitest_email_social_leads_and_visa(monkeypatch, tmp_path):
    import asyncio
    from openjarvis.core.types import ToolResult
    from openjarvis.server.meeting_routes import (
        DeviceHeartbeatRequest,
        _schedule_meeting_task_reminders,
        device_heartbeat,
        meeting_history,
        save_meeting_record,
    )
    from openjarvis.tools.app_control import SergioAppControlTool
    from openjarvis.tools.desktop_tools import DesktopActionTool, FaceApprovalTool
    from sergio_escritorio.voice import needs_agent

    recorded = []

    def fake_desktop_execute(self, **params):
        recorded.append(params)
        return ToolResult(tool_name="desktop_action", content="ejecutado en pantalla", success=True)

    def fake_face_execute(self, **params):
        return ToolResult(tool_name="face_approval", content="Rostro verificado 97 %", success=True)

    monkeypatch.setattr(DesktopActionTool, "execute", fake_desktop_execute)
    monkeypatch.setattr(FaceApprovalTool, "execute", fake_face_execute)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("openjarvis.server.meeting_routes.get_config_dir", lambda: tmp_path / ".openjarvis")

    tool = SergioAppControlTool()

    # 1. Multi-device control: ask Sergio on PC to start recording video from the phone
    phrase_phone = "Sergio, empieza a grabar video desde mi teléfono"
    assert needs_agent(phrase_phone)
    r_dev = tool.execute(
        action="device_control",
        platform="phone",
        device_command="record_video",
        content=phrase_phone,
    )
    assert r_dev.success and "record_video" in r_dev.content
    hb = asyncio.run(
        device_heartbeat(
            DeviceHeartbeatRequest(
                device_id="telefono-principal",
                kind="phone",
                name="iPhone del Señor",
            )
        )
    )
    assert any(cmd["action"] == "record_video" for cmd in hb["commands"])

    # 2. Meeting recording Pro with live timestamped notes + proactive task reminders + history
    minutes_record = {
        "id": "mtg-consejo-1",
        "titulo": "Consejo Directivo",
        "resumen": "Revisión ejecutiva de contratos y presupuesto.",
        "tareas": [
            {"quien": "Juan", "que": "Enviar contrato final firmado", "cuando": "mañana"},
            {"quien": "María", "que": "Validar presupuesto Q4", "cuando": "viernes"},
        ],
        "live_notes": ["[01:15] Cerrar cláusula de exclusividad", "[04:30] Confirmar firma digital"],
        "markdown": "# Consejo Directivo\n- Enviar contrato final firmado",
    }
    reminders_created = _schedule_meeting_task_reminders(minutes_record)
    assert len(reminders_created) == 2
    save_meeting_record(minutes_record)
    hist = asyncio.run(meeting_history(limit=5))
    assert any(m.get("titulo") == "Consejo Directivo" for m in hist["meetings"])

    # 3. Read emails and reply to them
    r_mail = tool.execute(
        action="email_inbox",
        platform="gmail",
        content="Responder a los correos urgentes de proveedores y clientes",
        auto_reply=True,
    )
    assert r_mail.success and "Bandeja de Entrada de Gmail leída y gestionada" in r_mail.content

    # 4. Student school platform + proactive exam reminders + Mini-Test
    r_study = tool.execute(
        action="academic_study",
        platform="canvas",
        content="Cálculo Diferencial y Leyes de Newton",
        when="Viernes 8:00 AM",
    )
    assert r_study.success
    assert "Mini-Test Interactivo para Estudiar" in r_study.content
    assert "Pregunta" in r_study.content or "Respuesta:" in r_study.content

    # 5. Make calls, reply to messages, upload Instagram Stories
    r_call = tool.execute(action="make_call", to="Dr. Martínez", content="Confirmar cita de las 17:00")
    assert r_call.success and "Llamada iniciada" in r_call.content

    r_msg = tool.execute(action="reply_messages", platform="whatsapp", to="Equipo", content="Ya voy en camino")
    assert r_msg.success and "Mensajes respondidos en Whatsapp" in r_msg.content

    r_ig = tool.execute(action="social_publish", platform="instagram", content="Entrenamiento completado hoy")
    assert r_ig.success and "Instagram" in r_ig.content

    # 6. Large-scale client lead generation
    r_leads = tool.execute(
        action="lead_generation",
        content="Clínicas estéticas y odontológicas premium",
        to="Quito y Cuenca",
    )
    assert r_leads.success and "Campaña de Búsqueda de Clientes a Gran Escala" in r_leads.content

    # 7. Apply for a VISA
    r_visa = tool.execute(
        action="visa_apply",
        to="Estados Unidos B1/B2",
        content="Renovación y cita prioritaria",
    )
    assert r_visa.success and "DS-160" in r_visa.content

def test_sergio_impossible_tasks_luxury_arbitrage_sniper_vault_and_biometrics(monkeypatch, tmp_path):
    from openjarvis.core.types import ToolResult
    from openjarvis.tools.app_control import SergioAppControlTool
    from openjarvis.tools.desktop_tools import DesktopActionTool

    recorded = []

    def fake_execute(self, **params):
        recorded.append(params)
        return ToolResult(tool_name="desktop_action", content="operado con éxito", success=True)

    monkeypatch.setattr(DesktopActionTool, "execute", fake_execute)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    tool = SergioAppControlTool()

    # 1. Hotel luxury arbitrage ($3k to $1.5k)
    r_hotel = tool.execute(
        action="hotel_arbitrage",
        title="Four Seasons George V Paris",
        to="París, Francia",
        when="15 al 20 de Noviembre",
        budget="3000 USD",
        price="1500 USD",
    )
    assert r_hotel.success
    assert "1500" in r_hotel.content and "3000" in r_hotel.content and "50" in r_hotel.content
    assert "Virtuoso" in r_hotel.content

    # 2. Michelin cancellation sniper
    recorded.clear()
    r_michelin = tool.execute(
        action="michelin_sniper",
        title="Disfrutar Barcelona",
        budget="2",
        when="Viernes 21:00",
        platform="resy",
    )
    assert r_michelin.success
    assert "Disfrutar Barcelona" in r_michelin.content
    assert "Playwright Stealth" in r_michelin.content

    # 3. 7-hour YouTube growth pipeline
    r_yt = tool.execute(
        action="youtube_growth_pipeline",
        content="curiosidades y hechos asombrosos del mundo",
        budget="7",
    )
    assert r_yt.success
    assert "7 Horas" in r_yt.content
    assert "resultaaquee" in r_yt.content

    # 4. Vertu-grade zero knowledge encrypted vault
    r_vault = tool.execute(
        action="vertu_vault",
        title="pasaporte_diplomatico_llave",
        content="DATOS_ULTRA_CONFIDENCIALES_DEL_SEÑOR",
        platform="credencial_maestra",
    )
    assert r_vault.success
    assert "Bóveda Vertu" in r_vault.content
    assert "AES-256-GCM" in r_vault.content

    # 5. Active health biometrics sync across wearables
    r_health = tool.execute(
        action="health_biometrics_sync",
        platform="Apple Watch Ultra & Anillo Oura",
    )
    assert r_health.success
    assert "Sincronización Biométrica" in r_health.content
    assert "HRV" in r_health.content

