"""Pragmatic Addressee Intent Classifier (Detección de Destinatario).

Distinguishes in real-time whether incoming speech is directed:
1. TO_AGENT (Sergio / J.A.R.V.I.S.): Commands, queries, imperatives, and system interactions.
2. TO_OTHER_HUMAN: Side-conversations, phone calls, interpersonal talk with family/colleagues.
3. TO_AMBIENT_MEDIA: Broadcast narration, TV series dialogue, movie scripts, and background noise.

Prevents Sergio from interrupting the user when conversing with third parties in the room.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Tuple


class AddresseeTarget(str, Enum):
    """Classified destination of human conversational utterance."""

    AGENT = "agente_sergio"
    OTHER_PERSON = "otra_persona_o_llamada"
    AMBIENT_MEDIA = "multimedia_o_serie"
    UNCERTAIN = "incierto_requiere_vocativo"


def _normalize(text: str) -> str:
    """Strip diacritics, convert to lower case, and normalize whitespace."""
    if not text:
        return ""
    clean = "".join(
        c
        for c in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(c)
    )
    return " ".join(clean.split())


class AddresseeClassifier:
    """Syntactic, pragmatic, and lexical classifier for speech destination."""

    # Explicit phrases indicating speaker is on phone or addressing a room companion
    _SIDE_CONVERSATION_MARKERS = [
        r"\b(no te hablo|no era para ti|hablo con otra persona|estoy hablando por telefono|no te estoy hablando)\b",
        r"\b(hablaba con|hablo con|estoy en llamada|estoy al telefono|me estan llamando)\b",
        r"\b(oye mama|mama|papa|amor|carino|hijo|hija|hermano|hermana|amigo|tia|tio|abuela|abuelo)\b",
        r"\b(pasame (el|la|los|las|eso)|alcanzame|sirveme|quieres comer|vamos a comer|que vas a querer)\b",
        r"\b(entonces le dije|fijate que|sabes que paso|te cuento que|me dijo que|estaba pensando que nosotros)\b",
        r"\b(te lo juro|en serio te dijo eso|no manches|no me digas|de verdad)\b",
    ]

    # Explicit directives and imperatives typical of assistant / agent queries
    _AGENT_DIRECTIVES = [
        r"\b(busca|buscar|encuentra|localiza|investiga|rastrea)\b",
        r"\b(abre|abrir|cierra|ejecuta|lanza|inicia|deten|para|cancela)\b",
        r"\b(dime|cuentame|explicame|leeme|resume|muestra|muestrame|ensename)\b",
        r"\b(pon|reproduce|cambia|sube|baja|silencia|pausa)\b",
        r"\b(reserva|compra|cotiza|arbitra|envia|manda|redacta)\b",
        r"\b(dile a|preguntale a|avisale a|escribele a|comentale a)\b",
        r"\b(que hora es|como esta el clima|cual es el precio|cuanto cuesta|que significa|como se dice)\b",
        r"\b(ayudame|necesito que|quiero que|puedes (abrir|buscar|decirme|ver|hacer))\b",
    ]

    # Dramatic and narrative cues typical of scripted series, movies, and YouTube monologues
    _MEDIA_DIALOGUE_PATTERNS = [
        r"\b(suscrib|dale like|activa la campanita|bienvenidos a(l| mi) canal|en este video|patrocinad)\b",
        r"\b(dispara|disparen|cuidado con el|no morire|el asesino|la policia|capitulo anterior|proximo capitulo)\b",
        r"\b(episodio|temporada|escena|detenganlo|traidor|fuego cruzado|manos arriba)\b",
        r"[\[\(](musica|music|aplausos|applause|risas|laughter)[\]\)]|♪",
    ]

    def __init__(self, agent_name: str = "Sergio") -> None:
        self.agent_name = agent_name.strip()
        self.name_pattern = re.compile(rf"\b{re.escape(_normalize(self.agent_name))}\b")

    def classify_utterance(
        self,
        text: str,
        recent_exchange_active: bool = False,
    ) -> Tuple[AddresseeTarget, float, str]:
        """Classify the intended recipient of the utterance.

        Returns:
            Tuple of (AddresseeTarget, confidence_score, explanation_verdict)
        """
        clean = _normalize(text)
        if not clean:
            return AddresseeTarget.UNCERTAIN, 0.0, "texto_vacio"

        # 1. Check for explicit exclusion markers (user telling Sergio to stay quiet / on phone)
        for pattern in self._SIDE_CONVERSATION_MARKERS:
            if re.search(pattern, clean):
                return (
                    AddresseeTarget.OTHER_PERSON,
                    0.95,
                    f"detectada_conversacion_con_tercero_o_llamada ('{pattern}')",
                )

        # 2. Check for scripted media patterns (movies, streams, TV)
        for pattern in self._MEDIA_DIALOGUE_PATTERNS:
            if re.search(pattern, clean):
                return (
                    AddresseeTarget.AMBIENT_MEDIA,
                    0.90,
                    f"patron_de_guion_o_medios_detectado ('{pattern}')",
                )

        # 3. Check for vocative invocation of agent's name
        named = bool(self.name_pattern.search(clean))
        # Third person references like "Sergio me dijo que..." are not vocative calls
        third_person = bool(
            re.search(
                rf"\b{re.escape(_normalize(self.agent_name))}\s+(dijo|dice|es|era|hizo|estaba|me dijo)\b",
                clean,
            )
        )

        if named and not third_person:
            # Explicit vocative addressing the agent
            return (
                AddresseeTarget.AGENT,
                0.98,
                "vocativo_explicito_dirigido_a_sergio",
            )

        if third_person:
            return (
                AddresseeTarget.OTHER_PERSON,
                0.88,
                "mencion_de_sergio_en_tercera_persona_charla_con_tercero",
            )

        # 4. Check for assistant directive keywords (imperatives/queries)
        directive_matches = 0
        for pattern in self._AGENT_DIRECTIVES:
            if re.search(pattern, clean):
                directive_matches += 1

        if directive_matches >= 1:
            if recent_exchange_active:
                # Follow-up in ongoing dialogue with clear command syntax
                return (
                    AddresseeTarget.AGENT,
                    0.85,
                    f"comando_directivo_en_hilo_activo ({directive_matches} directivas)",
                )
            else:
                # Command without vocative outside active window
                return (
                    AddresseeTarget.AGENT,
                    0.72,
                    f"estructura_de_comando_detectada ({directive_matches} directivas)",
                )

        # 5. Check sentence length and structure (long unstructured monologues are usually TV/talks)
        words = clean.split()
        if len(words) >= 35:
            return (
                AddresseeTarget.AMBIENT_MEDIA,
                0.82,
                "monologo_largo_tipico_de_video_o_reunion",
            )

        # 6. If an exchange was active and the turn is a short reply or follow-up question
        if recent_exchange_active and len(words) <= 12:
            return (
                AddresseeTarget.AGENT,
                0.70,
                "continuacion_corta_en_ventana_de_dialogo_abierta",
            )

        # 7. Default to other person / uncertain
        return (
            AddresseeTarget.UNCERTAIN,
            0.40,
            "sin_vocativo_ni_sintaxis_de_comando_descartado_por_defensa",
        )


__all__ = ["AddresseeTarget", "AddresseeClassifier"]
