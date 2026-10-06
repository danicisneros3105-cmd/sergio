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
    "tab_settings": {"es": "Ajustes", "en": "Settings", "pt": "Ajustes", "fr": "Réglages", "de": "Einstellungen",
                     "it": "Impostazioni"},
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
    "cams": {"es": "Cámaras en vivo", "en": "Live cameras", "pt": "Câmeras ao vivo", "fr": "Caméras en direct",
             "de": "Live-Kameras", "it": "Telecamere live"},
    "flight": {"es": "Vuelo en vivo", "en": "Live flight", "pt": "Voo ao vivo", "fr": "Vol en direct",
               "de": "Flug live", "it": "Volo live"},
    "place": {"es": "Lugar (ciudad, calle…)", "en": "Place (city, street…)", "pt": "Lugar (cidade, rua…)",
              "fr": "Lieu (ville, rue…)", "de": "Ort (Stadt, Straße…)", "it": "Luogo (città, via…)"},
    "flight_number": {"es": "Número de vuelo (AV123)", "en": "Flight number (BA123)",
                      "pt": "Número do voo (LA123)", "fr": "Numéro de vol (AF123)",
                      "de": "Flugnummer (LH123)", "it": "Numero di volo (AZ123)"},
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
    "globe": {"es": "God's Eye View", "en": "God's Eye View", "pt": "God's Eye View", "fr": "God's Eye View",
              "de": "God's Eye View", "it": "God's Eye View"},
    "cams": TEXTS["cams"],
    "flight": TEXTS["flight"],
    "blender": {"es": "Blender Pro", "en": "Blender Pro", "pt": "Blender Pro", "fr": "Blender Pro",
                "de": "Blender Pro", "it": "Blender Pro"},
    "video": {"es": "Video Pro", "en": "Video Pro", "pt": "Vídeo Pro", "fr": "Vidéo Pro", "de": "Video Pro",
              "it": "Video Pro"},
    "meeting": {"es": "Actas", "en": "Meeting notes", "pt": "Atas", "fr": "Comptes rendus",
                "de": "Protokolle", "it": "Verbali"},
    "profile": {"es": "Mi perfil", "en": "My profile", "pt": "Meu perfil", "fr": "Mon profil",
                "de": "Mein Profil", "it": "Il mio profilo"},
    "faces": {"es": "Caras", "en": "Faces", "pt": "Rostos", "fr": "Visages", "de": "Gesichter", "it": "Volti"},
    "blocking": TEXTS["blocking"],
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
