"""Sergio, international: your language and your country.

* The language Sergio speaks and the interface shows (Español, English,
  Português, Français, Deutsch, Italiano). By default, Windows' language.
* The country, for what changes from one place to another: the emergency
  number and the free mental-health line Sergio gives when someone is at
  risk (each one checked on its official source, see SOURCES), and where
  "Cuenca" or "Londres" is looked up first.

Choose them in the control center (Ajustes) or say «habla en inglés» /
«estoy en México».
"""

from __future__ import annotations

import locale
import re
from dataclasses import dataclass

LANGUAGES = {
    "es": "Español",
    "en": "English",
    "pt": "Português",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
}
LANGUAGE_NAMES_EN = {  # what the model is told
    "es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French", "de": "German", "it": "Italian",
}
# Sergio also speaks these (Gemini and Whisper know them); the interface
# texts fall back to English for them.
MORE_LANGUAGES = {
    "nl": ("Nederlands", "Dutch"), "pl": ("Polski", "Polish"), "ru": ("Русский", "Russian"),
    "uk": ("Українська", "Ukrainian"), "tr": ("Türkçe", "Turkish"), "ar": ("العربية", "Arabic"),
    "he": ("עברית", "Hebrew"), "hi": ("हिन्दी", "Hindi"), "bn": ("বাংলা", "Bengali"), "ur": ("اردو", "Urdu"),
    "fa": ("فارسی", "Persian"), "zh": ("中文", "Chinese"), "ja": ("日本語", "Japanese"), "ko": ("한국어", "Korean"),
    "id": ("Bahasa Indonesia", "Indonesian"), "ms": ("Bahasa Melayu", "Malay"), "vi": ("Tiếng Việt", "Vietnamese"),
    "th": ("ไทย", "Thai"), "tl": ("Filipino", "Filipino"), "sw": ("Kiswahili", "Swahili"), "el": ("Ελληνικά", "Greek"),
    "ro": ("Română", "Romanian"), "cs": ("Čeština", "Czech"), "hu": ("Magyar", "Hungarian"), "sv": ("Svenska", "Swedish"),
    "da": ("Dansk", "Danish"), "no": ("Norsk", "Norwegian"), "fi": ("Suomi", "Finnish"), "ca": ("Català", "Catalan"),
    "qu": ("Runa Simi", "Quechua"), "gn": ("Avañe'ẽ", "Guarani"),
}  # fmt: skip
for _code, (_native, _english) in MORE_LANGUAGES.items():
    LANGUAGES.setdefault(_code, _native)
    LANGUAGE_NAMES_EN.setdefault(_code, _english)
UI_LANGUAGES = ("es", "en", "pt", "fr", "de", "it")  # the interface is translated in these
# How Sergio addresses the owner in each language (the JARVIS «señor»).
SIR = {"es": "señor", "en": "sir", "pt": "senhor", "fr": "monsieur", "de": "mein Herr", "it": "signore"}


@dataclass(frozen=True)
class Country:
    code: str
    name: str
    language: str
    emergency: str
    crisis: str  # free mental-health / suicide-prevention line
    source: str


COUNTRIES = {
    c.code: c
    for c in (
        Country("EC", "Ecuador", "es", "ECU 911", "Línea 171, opción 6 (Ministerio de Salud, 7:00-20:00)",
                "https://www.salud.gob.ec/a-traves-de-la-linea-171-msp-ofrece-atencion-en-salud-mental/"),
        Country("CO", "Colombia", "es", "123", "Línea 192, opción 4 (Ministerio de Salud)",
                "https://www.minsalud.gov.co/"),
        Country("PE", "Perú", "es", "105 / 116", "Línea 113, opción 5 (MINSA, 24 h)",
                "https://andina.pe/agencia/noticia-linea-113-del-minsa-mas-60000-personas-recibieron-orientacion-psicologica-gratuita-1048068.aspx"),
        Country("CL", "Chile", "es", "131", "*4141 (Línea de Prevención del Suicidio, MINSAL, 24 h)",
                "https://www.minsal.cl/ministerio-de-salud-anuncio-fono-4141-de-prevencion-del-suicidio/"),
        Country("AR", "Argentina", "es", "911", "0800-345-1435 o 135 (Centro de Asistencia al Suicida, 24 h)",
                "https://www.asistenciaalsuicida.org.ar/"),
        Country("MX", "México", "es", "911", "Línea de la Vida 800 911 2000 (24 h)",
                "https://www.gob.mx/conasama"),
        Country("ES", "España", "es", "112", "024 (atención a la conducta suicida, 24 h)",
                "https://www.sanidad.gob.es/linea024/home.htm"),
        Country("US", "United States", "en", "911", "988 Suicide & Crisis Lifeline (call or text, 24/7)",
                "https://988lifeline.org/"),
        Country("CA", "Canada", "en", "911", "9-8-8 Suicide Crisis Helpline (call or text, 24/7)",
                "https://988.ca/"),
        Country("GB", "United Kingdom", "en", "999", "Samaritans 116 123 (free, 24/7)",
                "https://www.samaritans.org/"),
        Country("AU", "Australia", "en", "000", "Lifeline 13 11 14 (24/7)", "https://www.lifeline.org.au/"),
        Country("BR", "Brasil", "pt", "192 (SAMU) / 190", "CVV 188 (24 h, gratuito)", "https://cvv.org.br/"),
        Country("PT", "Portugal", "pt", "112", "SNS 24: 808 24 24 24 (aconselhamento psicológico)",
                "https://www.sns24.gov.pt/"),
        Country("FR", "France", "fr", "112 / 15", "3114 (prévention du suicide, 24h/24)", "https://3114.fr/"),
        Country("DE", "Deutschland", "de", "112", "TelefonSeelsorge 0800 111 0 111 (24 h, kostenlos)",
                "https://www.telefonseelsorge.de/"),
        Country("IT", "Italia", "it", "112", "Telefono Amico 02 2327 2327 (9:00-24:00)", "https://www.telefonoamico.it/"),
    )
}
WORLD = Country("", "Otro país", "en", "112", "findahelpline.com (free lines in every country)",
                "https://findahelpline.com/")
# Emergency numbers for the rest of the world (police / ambulance where they
# differ) — only the well-established ones. Elsewhere Sergio says 112 from a
# mobile phone (routed to the local service in most countries) and asks the
# user to confirm the local number.
EMERGENCY = {
    # Americas
    "CR": "911", "DO": "911", "SV": "911",
    "HN": "911", "PA": "911", "PY": "911", "UY": "911", "VE": "911", "PR": "911",
    "TT": "999",
    # Europe (112 everywhere in the EU; the UK also 999)
    "AT": "112", "BE": "112", "BG": "112", "HR": "112", "CY": "112", "CZ": "112", "DK": "112", "EE": "112",
    "FI": "112", "GR": "112", "HU": "112", "IE": "112 / 999", "LV": "112", "LT": "112", "LU": "112",
    "MT": "112", "NL": "112", "PL": "112", "RO": "112", "SK": "112", "SI": "112", "SE": "112",
    "NO": "112", "IS": "112", "CH": "112", "LI": "112", "UA": "112", "RU": "112", "TR": "112",
    "RS": "112", "BA": "112", "AL": "112", "MK": "112", "ME": "112", "MD": "112", "GE": "112",
    "AM": "112", "AZ": "112", "BY": "112",
    # Asia and Oceania
    "JP": "110 / 119", "CN": "110 / 120", "KR": "112 / 119", "TW": "110 / 119", "HK": "999", "MO": "999",
    "IN": "112", "PK": "15 / 1122", "BD": "999", "NP": "100 / 102", "ID": "112",
    "PH": "911", "VN": "113 / 115", "TH": "191 / 1669", "MY": "999", "SG": "999 / 995",
    "NZ": "111", "KZ": "112",
    # Middle East and Africa
    "IL": "100 / 101", "AE": "999", "SA": "911", "QA": "999", "KW": "112", "BH": "999",
    "JO": "911", "LB": "112 / 140", "EG": "122 / 123",
    "MA": "19 / 15", "ZA": "10111 / 112", "NG": "112", "KE": "999 / 112",
    "GH": "112", "TZ": "112", "UG": "999 / 112", "RW": "112",
    "ZW": "999", "ZM": "999", "BW": "999",
}  # fmt: skip
SOURCES = {c.code: c.source for c in COUNTRIES.values()}


def system_language() -> str:
    """Windows' language, if Sergio speaks it (else Spanish)."""
    try:
        code = (locale.getlocale()[0] or locale.getdefaultlocale()[0] or "es")[:2].lower()  # noqa: Q000
    except (ValueError, TypeError, AttributeError):
        code = "es"
    return code if code in LANGUAGES else "es"


def system_country() -> str:
    try:
        name = locale.getlocale()[0] or ""
    except (ValueError, TypeError):
        name = ""
    found = re.search(r"[_-]([A-Z]{2})\b", name)
    return found.group(1) if found and found.group(1) in COUNTRIES else ""


def country(code: str) -> Country:
    """The country's lines; anywhere without a checked crisis line: its
    emergency number and findahelpline.com (which lists every country)."""
    code = (code or "").upper()
    if code in COUNTRIES:
        return COUNTRIES[code]
    if code:
        return Country(code, code, "en", EMERGENCY.get(code, "112 (desde un celular; confirme el número local)"),
                       "findahelpline.com (free lines in your country)", WORLD.source)
    return WORLD


def crisis_text(code: str, lang: str = "es") -> str:
    """What Sergio says at once when someone may be at risk."""
    c = country(code)
    texts = {
        "es": ("Lo que me cuenta es importante y no quiero que lo lleve solo. Si corre peligro ahora, "
               "llame al {em}. Para hablar con alguien que sabe ayudar: {cr}. ¿Hay alguien de confianza "
               "que pueda estar con usted ahora? Sigo aquí."),
        "en": ("What you are telling me matters and I don't want you to carry it alone. If you are in "
               "danger now, call {em}. To talk to someone trained to help: {cr}. Is there someone you "
               "trust who can be with you now? I'm here."),
        "pt": ("O que você me conta é importante e não quero que carregue isso sozinho. Se estiver em "
               "perigo agora, ligue {em}. Para falar com alguém preparado para ajudar: {cr}. Há alguém "
               "de confiança que possa ficar com você agora? Estou aqui."),
        "fr": ("Ce que vous me dites compte et je ne veux pas que vous le portiez seul. Si vous êtes en "
               "danger maintenant, appelez le {em}. Pour parler à quelqu'un formé pour aider : {cr}. "
               "Y a-t-il une personne de confiance qui peut être avec vous ? Je suis là."),
        "de": ("Was Sie mir erzählen, ist wichtig, und Sie sollen das nicht allein tragen. Wenn Sie jetzt "
               "in Gefahr sind, rufen Sie die {em}. Um mit jemandem zu sprechen, der helfen kann: {cr}. "
               "Gibt es jemanden, dem Sie vertrauen und der jetzt bei Ihnen sein kann? Ich bin da."),
        "it": ("Quello che mi racconta è importante e non voglio che lo porti da solo. Se è in pericolo "
               "ora, chiami il {em}. Per parlare con qualcuno preparato ad aiutare: {cr}. C'è qualcuno "
               "di fiducia che può stare con lei ora? Sono qui."),
    }
    return texts.get(lang, texts["en"]).format(em=c.emergency, cr=c.crisis)


def crisis_line(code: str) -> str:
    c = country(code)
    return f"{c.emergency} · {c.crisis}"


# Risk words in every language Sergio speaks (the crisis lines never wait).
RISK_WORDS = (
    # español
    "suicid", "matarme", "quitarme la vida", "no quiero vivir", "hacerme daño", "hacerme dano",
    "cortarme", "autolesi", "mejor muerto", "acabar con todo", "quiero morir", "me quiero morir",
    # English
    "kill myself", "end my life", "want to die", "self harm", "self-harm", "hurt myself",
    "better off dead", "no reason to live",
    # português
    "me matar", "tirar minha vida", "quero morrer", "me machucar",
    # français
    "me tuer", "envie de mourir", "en finir", "me faire du mal",
    # Deutsch
    "mich umbringen", "sterben will", "selbstmord", "mir etwas antun",
    # italiano
    "uccidermi", "voglio morire", "farla finita", "farmi del male",
)  # fmt: skip


def at_risk(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in RISK_WORDS)


def speak_rule(lang: str) -> str:
    """The line added to Sergio's persona: which language, how to say «señor»."""
    name = LANGUAGE_NAMES_EN.get(lang, "Spanish")
    return (
        f" LANGUAGE: always answer in {name} (the user's chosen language), unless the "
        f"user clearly speaks to you in another language; then answer in that one. "
        + (f"Address the owner as «{SIR[lang]}»." if lang in SIR else
           "Address the owner with the respectful word for «sir» in that language.")
    )


ASK_LANGUAGE = re.compile(
    r"\b(habla|hablame|háblame|responde|contesta|cambia el idioma)\b.*\ben (espanol|español|ingles|inglés|"
    r"portugues|portugués|frances|francés|aleman|alemán|italiano)\b|\b(speak|talk|answer) (in )?(english|spanish|"
    r"portuguese|french|german|italian)\b",
    re.I,
)
_LANG_WORDS = {
    "espanol": "es", "español": "es", "spanish": "es", "ingles": "en", "inglés": "en", "english": "en",
    "portugues": "pt", "portugués": "pt", "portuguese": "pt", "frances": "fr", "francés": "fr",
    "french": "fr", "aleman": "de", "alemán": "de", "german": "de", "italiano": "it", "italian": "it",
}  # fmt: skip


def language_asked(text: str) -> str:
    """«habla en inglés» -> 'en' ('' if the text does not ask for a language)."""
    if not ASK_LANGUAGE.search(text):
        return ""
    for word, code in _LANG_WORDS.items():
        if re.search(rf"\b{word}\b", text, re.I):
            return code
    return ""


_COUNTRY_WORDS = {
    "ecuador": "EC", "colombia": "CO", "peru": "PE", "perú": "PE", "chile": "CL", "argentina": "AR",
    "mexico": "MX", "méxico": "MX", "espana": "ES", "españa": "ES", "estados unidos": "US",
    "usa": "US", "united states": "US", "canada": "CA", "canadá": "CA", "reino unido": "GB",
    "inglaterra": "GB", "uk": "GB", "united kingdom": "GB", "australia": "AU", "brasil": "BR",
    "brazil": "BR", "portugal": "PT", "francia": "FR", "france": "FR", "alemania": "DE",
    "germany": "DE", "deutschland": "DE", "italia": "IT", "italy": "IT",
}  # fmt: skip
ASK_COUNTRY = re.compile(r"\b(estoy en|vivo en|me mud[eé] a|i live in|i'?m in|moro (em|no|na))\s+(.+)", re.I)


def country_said(text: str) -> str:
    """«estoy en México» -> 'MX' ('' if no known country)."""
    found = ASK_COUNTRY.search(text)
    if not found:
        return ""
    rest = found.group(found.lastindex or 0).lower().strip(" .!?")
    for word, code in sorted(_COUNTRY_WORDS.items(), key=lambda kv: -len(kv[0])):
        if rest.startswith(word):
            return code
    return ""


# -- interface texts ------------------------------------------------------------------
TEXTS: dict[str, dict[str, str]] = {
    "tab_home": {"es": "Inicio", "en": "Home", "pt": "Início", "fr": "Accueil", "de": "Start", "it": "Home"},
    "tab_all": {"es": "Todo", "en": "All", "pt": "Tudo", "fr": "Tout", "de": "Alles", "it": "Tutto"},
    "tab_sergio": {"es": "Sergio", "en": "Sergio", "pt": "Sergio", "fr": "Sergio", "de": "Sergio", "it": "Sergio"},
    "tab_world": {"es": "Mundo", "en": "World", "pt": "Mundo", "fr": "Monde", "de": "Welt", "it": "Mondo"},
    "tab_guides": {"es": "Guías", "en": "Guides", "pt": "Guias", "fr": "Guides", "de": "Guides", "it": "Guide"},
    "tab_settings": {"es": "Configuración", "en": "Settings", "pt": "Configurações", "fr": "Réglages",
                     "de": "Einstellungen", "it": "Impostazioni"},
    "tab_chat": {"es": "Chat", "en": "Chat", "pt": "Chat", "fr": "Chat", "de": "Chat", "it": "Chat"},
    "tab_cowork": {"es": "Cowork", "en": "Cowork", "pt": "Cowork", "fr": "Cowork", "de": "Cowork", "it": "Cowork"},
    "tab_swarm": {"es": "Enjambre", "en": "Agent Swarm", "pt": "Enxame", "fr": "Essaim", "de": "Schwarm",
                  "it": "Sciame"},
    "d_health": {
        "es": "Su día, los datos del reloj y consejos",
        "en": "Your day, watch data and advice",
        "pt": "Seu dia, dados do relógio e conselhos",
        "fr": "Votre journée, la montre et des conseils",
        "de": "Dein Tag, Uhrdaten und Tipps",
        "it": "La tua giornata, l'orologio e consigli",
    },
    "d_night": {
        "es": "Pantalla cálida y tenue antes de dormir",
        "en": "A warm, dim screen before bed",
        "pt": "Tela quente e suave antes de dormir",
        "fr": "Écran chaud et doux avant de dormir",
        "de": "Warmer, gedimmter Bildschirm vor dem Schlaf",
        "it": "Schermo caldo e tenue prima di dormire",
    },
    "d_gym": {
        "es": "Ejercicios cortos de memoria y razonamiento",
        "en": "Short memory and reasoning drills",
        "pt": "Exercícios curtos de memória e raciocínio",
        "fr": "Exercices courts de mémoire et de raisonnement",
        "de": "Kurze Gedächtnis- und Denkübungen",
        "it": "Brevi esercizi di memoria e ragionamento",
    },
    "d_results": {
        "es": "Su progreso, con lo que dice la ciencia",
        "en": "Your progress, and what science says",
        "pt": "Seu progresso e o que diz a ciência",
        "fr": "Vos progrès, et ce que dit la science",
        "de": "Dein Fortschritt und was die Forschung sagt",
        "it": "I tuoi progressi e cosa dice la scienza",
    },
    "d_consult": {
        "es": "Hablar con calma, con técnicas de terapia",
        "en": "Talk it through, with therapy techniques",
        "pt": "Conversar com calma, com técnicas de terapia",
        "fr": "Parler au calme, avec des techniques de thérapie",
        "de": "In Ruhe reden, mit Therapietechniken",
        "it": "Parlare con calma, con tecniche di terapia",
    },
    "d_profile": {
        "es": "Lo que Sergio sabe de usted",
        "en": "What Sergio knows about you",
        "pt": "O que o Sergio sabe de você",
        "fr": "Ce que Sergio sait de vous",
        "de": "Was Sergio über dich weiß",
        "it": "Cosa sa Sergio di te",
    },
    "d_goals": {
        "es": "Sus metas y cómo van",
        "en": "Your goals and how they're going",
        "pt": "Suas metas e como estão indo",
        "fr": "Vos objectifs et où ils en sont",
        "de": "Deine Ziele und wie sie laufen",
        "it": "I tuoi obiettivi e come vanno",
    },
    "d_faces": {
        "es": "Su cara y las personas que conoce",
        "en": "Your face and people you know",
        "pt": "Seu rosto e as pessoas que conhece",
        "fr": "Votre visage et vos proches",
        "de": "Dein Gesicht und bekannte Personen",
        "it": "Il tuo volto e le persone che conosci",
    },
    "tab_health": {"es": "Salud", "en": "Health", "pt": "Saúde", "fr": "Santé", "de": "Gesundheit", "it": "Salute"},
    "tab_profile": {"es": "Perfil", "en": "Profile", "pt": "Perfil", "fr": "Profil", "de": "Profil", "it": "Profilo"},
    "cowork_hint": {"es": "Describa el resultado y siga con lo suyo. Lo delicado se lo pregunto aquí.",
                    "en": "Describe the outcome and carry on. I ask here before anything delicate.",
                    "pt": "Descreva o resultado e siga com o seu. O delicado eu pergunto aqui.",
                    "fr": "Décrivez le résultat et continuez. Je demande ici avant tout ce qui est délicat.",
                    "de": "Beschreiben Sie das Ergebnis. Heikles frage ich hier vorher.",
                    "it": "Descriva il risultato e continui. Le cose delicate le chiedo qui."},
    "cowork_goal": {"es": "Ej.: compara 3 portátiles para Blender en una tabla",
                    "en": "E.g.: compare 3 laptops for Blender in a table",
                    "pt": "Ex.: compare 3 notebooks para Blender numa tabela",
                    "fr": "Ex. : comparer 3 portables pour Blender dans un tableau",
                    "de": "Z. B.: 3 Laptops für Blender in einer Tabelle vergleichen",
                    "it": "Es.: confronta 3 portatili per Blender in una tabella"},
    "start": {"es": "Empezar", "en": "Start", "pt": "Começar", "fr": "Commencer", "de": "Starten", "it": "Inizia"},
    "planning": {"es": "Planificando…", "en": "Planning…", "pt": "Planejando…", "fr": "Planification…",
                 "de": "Plane…", "it": "Pianifico…"},
    "no_server": {"es": "No encuentro el servidor de Sergio.", "en": "Sergio's server is not reachable.",
                  "pt": "Não encontro o servidor do Sergio.", "fr": "Le serveur de Sergio est injoignable.",
                  "de": "Sergios Server ist nicht erreichbar.", "it": "Il server di Sergio non risponde."},
    "no_runs": {"es": "Todavía no hay trabajos.", "en": "No runs yet.", "pt": "Ainda não há trabalhos.",
                "fr": "Aucun travail pour l'instant.", "de": "Noch keine Aufträge.", "it": "Ancora nessun lavoro."},
    "needs_you": {"es": "le necesita", "en": "needs you", "pt": "precisa de você", "fr": "vous attend",
                  "de": "wartet auf Sie", "it": "la aspetta"},
    "step": {"es": "Paso", "en": "Step", "pt": "Passo", "fr": "Étape", "de": "Schritt", "it": "Passo"},
    "approve": {"es": "Aprobar", "en": "Approve", "pt": "Aprovar", "fr": "Approuver", "de": "Erlauben",
                "it": "Approva"},
    "deny": {"es": "Rechazar", "en": "Deny", "pt": "Recusar", "fr": "Refuser", "de": "Ablehnen", "it": "Rifiuta"},
    "swarm_hint": {"es": "Tareas en segundo plano: los pasos que se repiten se reparten entre subagentes a la vez.",
                   "en": "Background tasks: repeated steps are shared out to sub-agents at once.",
                   "pt": "Tarefas em segundo plano: passos repetidos vão para subagentes ao mesmo tempo.",
                   "fr": "Tâches de fond : les étapes répétées sont confiées à des sous-agents en parallèle.",
                   "de": "Hintergrundaufgaben: wiederholte Schritte laufen parallel in Unteragenten.",
                   "it": "Attività in background: i passi ripetuti vanno a sotto-agenti in parallelo."},
    "swarm_task": {"es": "Ej.: busca el precio de estos 40 productos", "en": "E.g.: find the price of these 40 products",
                   "pt": "Ex.: procure o preço destes 40 produtos", "fr": "Ex. : cherche le prix de ces 40 produits",
                   "de": "Z. B.: finde den Preis dieser 40 Produkte", "it": "Es.: cerca il prezzo di questi 40 prodotti"},
    "launch": {"es": "Lanzar", "en": "Launch", "pt": "Lançar", "fr": "Lancer", "de": "Los", "it": "Avvia"},
    "running_now": {"es": "En marcha", "en": "Running now", "pt": "Em andamento", "fr": "En cours",
                    "de": "Läuft gerade", "it": "In corso"},
    "cancel_last": {"es": "Cancelar la última", "en": "Cancel the last one", "pt": "Cancelar a última",
                    "fr": "Annuler la dernière", "de": "Letzte abbrechen", "it": "Annulla l'ultima"},
    "nothing_running": {"es": "Nada en marcha.", "en": "Nothing running.", "pt": "Nada em andamento.",
                        "fr": "Rien en cours.", "de": "Nichts läuft.", "it": "Niente in corso."},
    "health_hint": {"es": "Su salud, su sueño y su mente.", "en": "Your health, your sleep and your mind.",
                    "pt": "Sua saúde, seu sono e sua mente.", "fr": "Votre santé, votre sommeil et votre esprit.",
                    "de": "Ihre Gesundheit, Ihr Schlaf und Ihr Kopf.", "it": "La sua salute, il sonno e la mente."},
    "multitasking": {"es": "Multitasking (isla dividida)", "en": "Multitasking (split island)",
                     "pt": "Multitarefa (ilha dividida)", "fr": "Multitâche (île divisée)",
                     "de": "Multitasking (geteilte Insel)", "it": "Multitasking (isola divisa)"},
    "hide_notch": {"es": "Esconder el notch", "en": "Hide the notch", "pt": "Esconder o notch",
                   "fr": "Masquer l'encoche", "de": "Notch ausblenden", "it": "Nascondi il notch"},
    "type_here": {"es": "Escríbele a Sergio…", "en": "Write to Sergio…", "pt": "Escreva para o Sergio…",
                  "fr": "Écrivez à Sergio…", "de": "Schreib Sergio…", "it": "Scrivi a Sergio…"},
    "talk": {"es": "Hablar", "en": "Talk", "pt": "Falar", "fr": "Parler", "de": "Sprechen", "it": "Parla"},
    "brain": {"es": "Cerebro", "en": "Brain", "pt": "Cérebro", "fr": "Cerveau", "de": "Gehirn", "it": "Cervello"},
    "mic": {"es": "Micrófono", "en": "Microphone", "pt": "Microfone", "fr": "Micro", "de": "Mikrofon",
            "it": "Microfono"},
    "last_answer": {"es": "ÚLTIMA RESPUESTA", "en": "LAST ANSWER", "pt": "ÚLTIMA RESPOSTA",
                    "fr": "DERNIÈRE RÉPONSE", "de": "LETZTE ANTWORT", "it": "ULTIMA RISPOSTA"},
    "ask_me": {"es": "Pregúntame algo o dime «Sergio, …».", "en": "Ask me anything or say «Sergio, …».",
               "pt": "Pergunte algo ou diga «Sergio, …».", "fr": "Demandez-moi ou dites « Sergio, … ».",
               "de": "Frag mich etwas oder sag „Sergio, …“.", "it": "Chiedimi qualcosa o di' «Sergio, …»."},
    "language": {"es": "Idioma", "en": "Language", "pt": "Idioma", "fr": "Langue", "de": "Sprache",
                 "it": "Lingua"},
    "country": {"es": "País", "en": "Country", "pt": "País", "fr": "Pays", "de": "Land", "it": "Paese"},
    "emergency": {"es": "Emergencias y apoyo", "en": "Emergency and support", "pt": "Emergência e apoio",
                  "fr": "Urgences et soutien", "de": "Notruf und Hilfe", "it": "Emergenze e supporto"},
    "settings_hint": {
        "es": "Sergio habla y te atiende en tu idioma; el país decide los números de emergencia.",
        "en": "Sergio speaks your language; the country sets the emergency numbers.",
        "pt": "O Sergio fala o seu idioma; o país define os números de emergência.",
        "fr": "Sergio parle votre langue ; le pays fixe les numéros d'urgence.",
        "de": "Sergio spricht deine Sprache; das Land bestimmt die Notrufnummern.",
        "it": "Sergio parla la tua lingua; il paese decide i numeri di emergenza."},
    "show": {"es": "Mostrar", "en": "Show", "pt": "Mostrar", "fr": "Afficher", "de": "Zeigen", "it": "Mostra"},
    "follow": {"es": "Seguir", "en": "Follow", "pt": "Seguir", "fr": "Suivre", "de": "Folgen", "it": "Segui"},
    "blocking": {"es": "Bloqueo", "en": "Blocking", "pt": "Bloqueio", "fr": "Blocage", "de": "Sperren",
                 "it": "Blocco"},
}

SECTIONS = {  # the «Todo» tab: every part of Sergio, one tap away
    "organizer": {"es": "Organizador", "en": "Organizer", "pt": "Organizador", "fr": "Organiseur",
                  "de": "Organizer", "it": "Organizer"},
    "goals": {"es": "Mis metas", "en": "My goals", "pt": "Minhas metas", "fr": "Mes objectifs",
              "de": "Meine Ziele", "it": "I miei obiettivi"},
    "health": {"es": "Mi salud", "en": "My health", "pt": "Minha saúde", "fr": "Ma santé",
               "de": "Gesundheit", "it": "La mia salute"},
    "consult": {"es": "Consulta", "en": "Counselling", "pt": "Consulta", "fr": "Consultation",
                "de": "Gespräch", "it": "Consulto"},
    "gym": {"es": "Gimnasio mental", "en": "Mind gym", "pt": "Academia mental", "fr": "Gym mentale",
            "de": "Gehirntraining", "it": "Palestra mentale"},
    "results": {"es": "Mis resultados", "en": "My results", "pt": "Meus resultados", "fr": "Mes résultats",
                "de": "Ergebnisse", "it": "Risultati"},
    "camera": {"es": "Sergio ve", "en": "Sergio sees", "pt": "Sergio vê", "fr": "Sergio voit",
               "de": "Sergio sieht", "it": "Sergio vede"},
    "holo": {"es": "Hologramas", "en": "Holograms", "pt": "Hologramas", "fr": "Hologrammes",
             "de": "Hologramme", "it": "Ologrammi"},
    "blender": {"es": "Blender Pro", "en": "Blender Pro", "pt": "Blender Pro", "fr": "Blender Pro",
                "de": "Blender Pro", "it": "Blender Pro"},
    "video": {"es": "Video Pro", "en": "Video Pro", "pt": "Vídeo Pro", "fr": "Vidéo Pro", "de": "Video Pro",
              "it": "Video Pro"},
    "meeting": {"es": "Actas", "en": "Meeting notes", "pt": "Atas", "fr": "Comptes rendus",
                "de": "Protokolle", "it": "Verbali"},
    "profile": {"es": "Mi perfil", "en": "My profile", "pt": "Meu perfil", "fr": "Mon profil",
                "de": "Mein Profil", "it": "Il mio profilo"},
    "faces": {"es": "Caras", "en": "Faces", "pt": "Rostos", "fr": "Visages", "de": "Gesichter", "it": "Volti"},
    "agents": {"es": "Agentes", "en": "Agents", "pt": "Agentes", "fr": "Agents", "de": "Agenten", "it": "Agenti"},
    "blocking": TEXTS["blocking"],
    "night": {"es": "Night Shift", "en": "Night Shift", "pt": "Night Shift", "fr": "Night Shift",
              "de": "Night Shift", "it": "Night Shift"},
    "lock": {"es": "Bloquear PC", "en": "Lock PC", "pt": "Bloquear PC", "fr": "Verrouiller", "de": "PC sperren",
             "it": "Blocca PC"},
}


def t(key: str, lang: str = "es") -> str:
    table = TEXTS.get(key) or SECTIONS.get(key) or {}
    if lang not in UI_LANGUAGES:
        lang = "en"
    return table.get(lang) or table.get("es") or key


__all__ = [
    "COUNTRIES", "EMERGENCY", "LANGUAGES", "UI_LANGUAGES", "SECTIONS", "TEXTS", "at_risk", "country", "country_said", "crisis_line",
    "crisis_text", "language_asked", "speak_rule", "system_country", "system_language", "t",
]  # fmt: skip
