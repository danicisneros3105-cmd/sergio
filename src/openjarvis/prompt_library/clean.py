"""Turn raw prompt files into clean passages Sergio may learn from.

Three rules: lines that give the model another identity (another assistant's
name, maker, cutoff date) are dropped; remaining names of other assistants and
companies become neutral words; passages written to switch safety off
(jailbreaks, "no rules" personas) are dropped whole.
"""

from __future__ import annotations

import re
from typing import Iterator, List, Tuple

# Other assistants and products seen in the collections (case-sensitive, so
# ordinary words such as "cursor" or "bolt" in lower case are left alone).
ASSISTANTS = (
    "Claude Code",
    "Claude",
    "ChatGPT",
    "GPT-5",
    "GPT-4o",
    "GPT-4",
    "GPT-3.5",
    "GPT",
    "Gemini",
    "Bard",
    "Grok",
    "Copilot",
    "Cursor",
    "Devin",
    "Manus",
    "Lovable",
    "Bolt",
    "Replit",
    "Windsurf",
    "Cascade",
    "Codeium",
    "Perplexity",
    "Bing",
    "Sydney",
    "Kimi",
    "DeepSeek",
    "Qwen",
    "Tongyi",
    "Doubao",
    "Trae",
    "Le Chat",
    "Llama",
    "Cline",
    "Roo Code",
    "Aider",
    "Augment",
    "Kiro",
    "Junie",
    "Cluely",
    "Lovart",
    "Codex",
    "v0",
    "Poke",
    "Lumo",
    "Leo",
    "Dia",
    "Fellou",
    "Genspark",
    "Notte",
    "MultiOn",
    "Phind",
    "Kagi",
    "Raycast",
    "Xcode",
    "Qoder",
    "CodeBuddy",
    "Orchids",
    "Sesame",
    "Blackbox",
    "ChatGLM",
    "GLM",
    "Meta AI",
    "My AI",
    "Zoe",
    "Eos",
    "GAIA",
)
COMPANIES = (
    "Anthropic",
    "OpenAI",
    "Google DeepMind",
    "DeepMind",
    "Google",
    "xAI",
    "Microsoft",
    "Moonshot AI",
    "Moonshot",
    "Alibaba",
    "ByteDance",
    "Mistral AI",
    "Mistral",
    "Meta",
    "Apple",
    "Amazon",
    "Vercel",
    "Anysphere",
    "Cognition",
    "Perplexity AI",
    "Zhipu",
    "Z.ai",
    "JetBrains",
    "Notion",
    "Canva",
    "Brave",
    "Opera",
    "DuckDuckGo",
    "Proton",
    "Databricks",
    "Evernote",
    "Discord",
    "Telegram",
    "WhatsApp",
    "Snapchat",
    "Roblox",
    "Shapes Inc",
    "Inflection",
)


def names_pattern(words: Tuple[str, ...], flags: int = 0) -> re.Pattern[str]:
    ordered = sorted(set(words), key=len, reverse=True)
    body = "|".join(re.escape(w) for w in ordered)
    return re.compile(r"(?<![\w-])(?:" + body + r")(?![\w-])", flags)


_ASSISTANT = names_pattern(ASSISTANTS)
_COMPANY = names_pattern(COMPANIES)
_ANY = names_pattern(ASSISTANTS + COMPANIES)

_IDENTITY = re.compile(
    r"\b(you are|you're|your name is|i am|i'm|this is|you were|you have been|"
    r"created by|built by|developed by|trained by|made by|powered by|"
    r"eres|te llamas|creado por|desarrollado por|entrenado por)\b",
    re.I,
)
_DATED = re.compile(
    r"knowledge cut-?off|training data|current date|today'?s date|"
    r"model (name|id|family)|fecha (de corte|actual)",
    re.I,
)

JAILBREAK = re.compile(
    r"jail-?break|do anything now|\bDAN\b|developer mode|god ?mode|"
    r"ignore (all |any )?(of )?(the |your )?(previous|prior|above|earlier) (instructions|rules|prompts)|"
    r"(no|without|free of|free from) (any )?(ethical|moral|content|safety) "
    r"(guidelines|restrictions|limits|filters|boundaries|principles)|"
    r"without (any )?(restrictions|filters|censorship|limitations)|"
    r"\buncensored\b|\bunfiltered\b|\bamoral\b|\bunhinged\b|"
    r"bypass (the |your |any )?(filters?|safety|guidelines|policy|policies|restrictions)|"
    r"(have|has) no (rules|limits|restrictions|boundaries)|not bound by|"
    r"never refuse|cannot refuse|can'?t refuse|must not refuse|"
    r"break (free|out) of|escape the matrix|"
    r"sin (restricciones|censura|filtros|l[ií]mites [eé]ticos)",
    re.I,
)

# Secrets that sometimes ride along in leaked prompts.
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|"
    r"xox[abpr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})"
)
_URL = re.compile(r"https?://\S+")
_MODEL_ID = re.compile(r"\b(?:gpt|claude|gemini|llama|qwen|grok)-?\d[\w.-]*", re.I)


def is_jailbreak(text: str) -> bool:
    return bool(JAILBREAK.search(text or ""))


def is_jailbreak_file(name: str, text: str) -> bool:
    """Good prompts mention jailbreaks to refuse them; a jailbreak is dense with them."""
    if "jailbreak" in name.lower():
        return True
    hits = len(JAILBREAK.findall(text or ""))
    return hits >= 4 and hits * 3000 >= len(text or "")


def neutral(text: str) -> str:
    """Names of other assistants and companies become neutral words."""
    text = _COMPANY.sub("la empresa", text)
    text = _MODEL_ID.sub("el asistente", text)
    return _ASSISTANT.sub("el asistente", text)


def clean_text(text: str) -> str:
    """Drop identity lines, secrets and links; neutralize the rest."""
    kept: List[str] = []
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        if _DATED.search(line):
            continue
        if _IDENTITY.search(line) and _ANY.search(line):
            continue
        line = _SECRET.sub("[clave omitida]", line)
        line = _URL.sub("[enlace]", line)
        kept.append(line.rstrip())
    out = neutral("\n".join(kept))
    return re.sub(r"\n{3,}", "\n\n", out).strip()


_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_XML_HEADING = re.compile(r"^\s*<([a-z_][a-z0-9_-]{2,40})>\s*$", re.I)


def passages(
    text: str, title: str, *, target: int = 900, limit: int = 1500
) -> Iterator[Tuple[str, str]]:
    """Split a cleaned prompt into (heading, passage) pieces of about *target*
    characters, breaking at headings and blank lines; one jailbreak sentence
    drops its whole passage."""
    heading = title
    buf: List[str] = []
    size = 0

    def flush() -> Iterator[Tuple[str, str]]:
        body = "\n".join(buf).strip()
        if len(body) >= 80 and not is_jailbreak(body):
            yield heading, body

    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        first = block.split("\n", 1)[0]
        match = _HEADING.match(first) or _XML_HEADING.match(first)
        if match and size >= 200:
            yield from flush()
            buf, size = [], 0
        if match:
            name = (
                match.group(2)
                if match.re is _HEADING
                else match.group(1).replace("_", " ")
            )
            name = name.strip()[:80]
            heading = f"{title} · {name}" if title else name
        while len(block) > limit:
            cut = block.rfind(". ", 0, limit)
            cut = cut + 1 if cut > limit // 2 else limit
            if buf:
                yield from flush()
                buf, size = [], 0
            buf = [block[:cut]]
            yield from flush()
            buf, size = [], 0
            block = block[cut:].strip()
        if size + len(block) > target and size >= 200:
            yield from flush()
            buf, size = [], 0
        buf.append(block)
        size += len(block) + 2
    yield from flush()


__all__ = [
    "ASSISTANTS",
    "COMPANIES",
    "JAILBREAK",
    "clean_text",
    "is_jailbreak",
    "is_jailbreak_file",
    "names_pattern",
    "neutral",
    "passages",
]
