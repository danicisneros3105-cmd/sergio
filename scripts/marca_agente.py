"""Sergio's name, look and language on the coding agent (extensions/clacky).

The agent is vendored from OpenClacky (MIT). Its web interface ships with its
own name, logo, indigo colours, an update channel and the vendor's paid key
gateway; inside Sergio everything in sight is Sergio's (AGENTS.md: «Todo es
Sergio»). This script is the whole patch, written out so a fresh copy of the
upstream code can be patched again with one command:

    python3 scripts/marca_agente.py           # apply (safe to run twice)
    python3 scripts/marca_agente.py --check   # exit 1 if anything is unpatched

Only what is visible changes: names, logo, colours, language, and the vendor's
promotions. Identifiers, storage keys, paths and behaviour stay as they are.
The credit to the original project stays in Ajustes > Acerca de, in NOTICE and
in extensions/clacky/LICENSE.txt.

Files it relies on (kept in the repository next to the agent's web files):
``web/sergio/es.js`` (Spanish for every English text), ``web/sergio/skin.css``
(Sergio's palette and letters), ``web/sergio/icon.png`` (Sergio's icon) and
``web/sergio/josefin-sans.woff2`` (the wordmark letters, SIL OFL).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "extensions" / "clacky" / "lib" / "clacky"
WEB = AGENT / "web"
OWN_FILES = ("es.js", "skin.css", "icon.png", "josefin-sans.woff2")

CREDIT = (
    '<p class="sergio-credit">Agente de código de Sergio, basado en OpenClacky '
    "(licencia MIT) con cambios de Sergio. La licencia original está en "
    "extensions/clacky/LICENSE.txt.</p>"
)

# (file relative to lib/clacky, exact text, replacement). A replacement that
# keeps the original text (an insertion) is recognised as already applied.
PATCHES: list[tuple[str, str, str]] = [
    # -- The page: language, icon, Sergio's styles and Spanish texts --------
    ("web/index.html", '<html lang="en" id="html-root"', '<html lang="es" id="html-root"'),
    (
        "web/index.html",
        '<link rel="icon" type="image/svg+xml" href="/favicon.svg">',
        '<link rel="icon" type="image/png" href="/sergio/icon.png">',
    ),
    (
        "web/index.html",
        '<link rel="apple-touch-icon" href="/apple-touch-icon-180.png">',
        '<link rel="apple-touch-icon" href="/sergio/icon.png">',
    ),
    (
        "web/index.html",
        '<link rel="stylesheet" href="/app.css">',
        '<link rel="stylesheet" href="/app.css">\n  <link rel="stylesheet" href="/sergio/skin.css">',
    ),
    (
        "web/index.html",
        '<script src="/i18n.js"></script>',
        '<script src="/sergio/es.js"></script>\n<script src="/i18n.js"></script>',
    ),
    (
        "web/index.html",
        '<span class="about-value" id="about-app-name">OpenClacky</span>',
        '<span class="about-value" id="about-app-name">Sergio · Agente de código</span>',
    ),
    (
        "web/index.html",
        '<div class="settings-about-links">',
        CREDIT + '\n            <div class="settings-about-links" hidden>',
    ),
    (
        "web/index.html",
        'data-i18n="onboard.device.card.title">OpenClacky AI Keys</span>',
        'data-i18n="onboard.device.card.title">Claves de IA de un tercero</span>',
    ),
    (
        "web/index.html",
        'data-i18n="onboard.device.success.btn">Start using Clacky</span>',
        'data-i18n="onboard.device.success.btn">Empezar a usar Sergio</span>',
    ),
    (
        "web/index.html",
        '<button id="settings-btn-lang-en"',
        '<button id="settings-btn-lang-es" class="settings-lang-btn" data-lang="es">Español</button>\n'
        '              <button id="settings-btn-lang-en"',
    ),
    (
        "web/index.html",
        '<button id="setup-btn-lang-zh" class="setup-lang-btn active">中文</button>',
        '<button id="setup-btn-lang-es" class="setup-lang-btn active">Español</button>\n'
        '          <button id="setup-btn-lang-zh" class="setup-lang-btn">中文</button>',
    ),
    (
        "web/index.html",
        '<span id="setup-btn-lang-next-label">继续</span>',
        '<span id="setup-btn-lang-next-label">Continuar</span>',
    ),
    (
        "web/design-sample.html",
        "<title>OpenClacky · Design Sample v2</title>",
        "<title>Sergio · Design Sample v2</title>",
    ),
    (
        "web/design-sample.html",
        '<span id="header-logo">OpenClacky</span>',
        '<span id="header-logo">Sergio</span>',
    ),
    # -- Spanish first, English as the fallback ------------------------------
    ("web/i18n.js", 'const DEFAULT_LANG = "en";', 'const DEFAULT_LANG = "es";'),
    (
        "web/i18n.js",
        "  const TRANSLATIONS = {\n",
        "  const TRANSLATIONS = {\n"
        "    // Sergio: Spanish (sergio/es.js) first; English stays the fallback.\n"
        "    es: window.SERGIO_ES || {},\n",
    ),
    (
        "web/i18n.js",
        "let str = dict[key] ?? TRANSLATIONS[DEFAULT_LANG][key] ?? key;",
        "let str = dict[key] ?? TRANSLATIONS[DEFAULT_LANG][key] ?? TRANSLATIONS.en[key] ?? key;",
    ),
    (
        "web/i18n.js",
        "if (dict[key] == null && TRANSLATIONS[DEFAULT_LANG][key] == null) break;",
        "if (dict[key] == null && TRANSLATIONS[DEFAULT_LANG][key] == null && TRANSLATIONS.en[key] == null) break;",
    ),
    (
        "web/i18n.js",
        'const primary = lang === "zh" ? "思考中" : "Thinking";',
        'const primary = lang === "zh" ? "思考中" : lang === "es" ? "Pensando" : "Thinking";',
    ),
    (
        "web/i18n.js",
        "const verbs = THINKING_VERBS[lang] || THINKING_VERBS.en;",
        'const verbs = lang === "es" ? null : (THINKING_VERBS[lang] || THINKING_VERBS.en);',
    ),
    ("web/i18n.js", '"Start using Clacky"', '"Start using Sergio"'),
    ("web/i18n.js", "\"Clacky's channel system has", '"The agent\'s channel system has'),
    ("web/i18n.js", '"Clacky 频道系统', '"智能体频道系统'),
    # -- The name and the mark ---------------------------------------------
    ("web/features/brand/view.js", '_applyBrandName("OpenClacky");', '_applyBrandName("Sergio");'),
    (
        "web/features/brand/view.js",
        'logoText.textContent   = "OpenClacky";',
        'logoText.textContent   = "Sergio";',
    ),
    (
        "web/features/brand/view.js",
        '    logoImg.src           = "/logo_nav_dark.png";\n'
        '    logoImg.alt           = "OpenClacky";\n'
        '    logoImg.style.display = "";\n'
        '    if (brandWrap) brandWrap.classList.add("has-logo");\n'
        '    _applyFavicon("/favicon.svg");',
        "    // Sergio: the name is the mark; no picture logo.\n"
        '    logoImg.style.display = "none";\n'
        '    logoImg.removeAttribute("src");\n'
        '    if (brandWrap) brandWrap.classList.remove("has-logo");\n'
        '    _applyFavicon("/sergio/icon.png");',
    ),
    ("web/settings.js", 'Brand.applyBrandName("OpenClacky");', 'Brand.applyBrandName("Sergio");'),
    ("web/features/share/store.js", 'const DEFAULT_NAME     = "OpenClacky";', 'const DEFAULT_NAME     = "Sergio";'),
    (
        "web/features/share/store.js",
        'const DEFAULT_HOMEPAGE = "https://www.openclacky.com/";',
        "const DEFAULT_HOMEPAGE = null;",
    ),
    (
        "server/http_server.rb",
        '(product_name.nil? || product_name.strip.empty?) ? "OpenClacky" : product_name',
        '(product_name.nil? || product_name.strip.empty?) ? "Sergio" : product_name',
    ),
    (
        "server/http_server.rb",
        'product_name = brand.product_name || "OpenClacky"',
        'product_name = brand.product_name || "Sergio"',
    ),
    (
        "server/http_server.rb",
        'logo_url     = brand.logo_url || "/logo_nav_dark.png"\n'
        '            logo_hidden  = logo_url.start_with?("http://", "https://") ? \'style="display:none"\' : ""',
        'logo_url     = brand.logo_url || ""\n'
        '            logo_hidden  = (logo_url.empty? || logo_url.start_with?("http://", "https://")) ? \'style="display:none"\' : ""',
    ),
    # -- No vendor gateway, no vendor update channel -----------------------
    (
        "web/settings.js",
        "_providers = providerData.providers || [];",
        '_providers = (providerData.providers || []).filter(p => p.id !== "openclacky");',
    ),
    (
        "web/components/onboard.js",
        "_providers = data.providers || [];",
        '_providers = (data.providers || []).filter(p => p.id !== "openclacky");',
    ),
    (
        "web/features/version/store.js",
        "_needsUpdate = !!data.needs_update;",
        "_needsUpdate = false;  // Sergio updates the agent with its own update command",
    ),
    # -- Spanish in the first-run language step ------------------------------
    (
        "web/components/onboard.js",
        "    btnNext.addEventListener(\"click\", async () => {\n      _showSetupStep(\"key\");",
        '    const btnEs = $("setup-btn-lang-es");\n'
        '    if (btnEs) btnEs.addEventListener("click", () => {\n'
        '      _selectedLang = "es";\n'
        '      I18n.setLang("es");\n'
        '      _updateLangBtns("es");\n'
        "    });\n\n"
        "    btnNext.addEventListener(\"click\", async () => {\n      _showSetupStep(\"key\");",
    ),
    (
        "web/components/onboard.js",
        '    btnZh.classList.toggle("active", lang === "zh");\n'
        '    if (nextLabel) nextLabel.textContent = lang === "zh" ? "继续" : "Continue";',
        '    btnZh.classList.toggle("active", lang === "zh");\n'
        '    const btnEs = $("setup-btn-lang-es");\n'
        '    if (btnEs) btnEs.classList.toggle("active", lang === "es");\n'
        '    if (nextLabel) nextLabel.textContent = lang === "zh" ? "继续" : lang === "es" ? "Continuar" : "Continue";',
    ),
    # -- Spanish on the chips under the first message and in session names --
    (
        "web/features/new-session/view.js",
        '  function _isZh() {\n    return I18n.lang && I18n.lang().startsWith("zh");\n  }\n',
        '  function _isZh() {\n    return I18n.lang && I18n.lang().startsWith("zh");\n  }\n\n'
        "  // Sergio: Spanish labels for the chips under the first message.\n"
        '  function _isEs() {\n    return I18n.lang && I18n.lang() === "es";\n  }\n',
    ),
    (
        "web/features/new-session/view.js",
        ': (zh ? "选择项目" : "Project");',
        ': (zh ? "选择项目" : _isEs() ? "Proyecto" : "Project");',
    ),
    (
        "web/features/new-session/view.js",
        'const nameLabel = nameVal || (zh ? "会话名称" : "Name");',
        'const nameLabel = nameVal || (zh ? "会话名称" : _isEs() ? "Nombre" : "Name");',
    ),
    (
        "web/features/new-session/view.js",
        'let modelLabel = zh ? "模型" : "Model";',
        'let modelLabel = zh ? "模型" : _isEs() ? "Modelo" : "Model";',
    ),
    (
        "web/features/new-session/view.js",
        ': (zh ? "工作目录" : "Directory");',
        ': (zh ? "工作目录" : _isEs() ? "Carpeta" : "Directory");',
    ),
    (
        "web/features/new-session/view.js",
        'const dirChip = _makeChip(dirIcon, dirShort || (zh ? "工作目录" : "Directory"), _openDirPopover);',
        'const dirChip = _makeChip(dirIcon, (dirShort === "clacky_workspace" && _isEs() ? "Carpeta de trabajo" : dirShort)'
        ' || (zh ? "工作目录" : _isEs() ? "Carpeta" : "Directory"), _openDirPopover);',
    ),
    (
        "web/features/new-session/view.js",
        'const initLabel = zh ? "初始化项目" : "Init project";',
        'const initLabel = zh ? "初始化项目" : _isEs() ? "Crear proyecto" : "Init project";',
    ),
    (
        "web/features/new-session/store.js",
        "const m = s.name && s.name.match(/^Session (\\d+)$/);",
        "const m = s.name && s.name.match(/^(?:Session|Sesión) (\\d+)$/);",
    ),
    (
        "web/features/new-session/store.js",
        'return "Session " + (maxN + 1);',
        'return (I18n.lang && I18n.lang() === "es" ? "Sesión " : "Session ") + (maxN + 1);',
    ),
    ("web/sessions.js", "/^Session (\\d+)$/", "/^(?:Session|Sesión) (\\d+)$/"),
    (
        "web/sessions.js",
        'return "Session " + (maxN + 1);',
        'return (I18n.lang && I18n.lang() === "es" ? "Sesión " : "Session ") + (maxN + 1);',
    ),
    (
        "web/sessions.js",
        'const name = "Session " + (maxN + 1);',
        'const name = (I18n.lang && I18n.lang() === "es" ? "Sesión " : "Session ") + (maxN + 1);',
    ),
    ("web/features/tasks/store.js", "/^Session (\\d+)$/", "/^(?:Session|Sesión) (\\d+)$/"),
    (
        "web/features/tasks/store.js",
        'name: "Session " + (maxN + 1)',
        'name: (I18n.lang && I18n.lang() === "es" ? "Sesión " : "Session ") + (maxN + 1)',
    ),
    # -- The built-in extensions read their Spanish from sergio/es.js --------
    (
        "default_extensions/advisor/panels/advisor/view.js",
        "const v = (DICT[lang] && DICT[lang][key]) || DICT.en[key];",
        'const v = (lang === "es" && window.SERGIO_ES_EXT && window.SERGIO_ES_EXT.advisor[key])'
        " || (DICT[lang] && DICT[lang][key]) || DICT.en[key];",
    ),
    (
        "default_extensions/meeting/panels/meeting/view.js",
        "const dict = MEETING_I18N[lang] || MEETING_I18N.en;",
        'const dict = (lang === "es" && window.SERGIO_ES_EXT && window.SERGIO_ES_EXT.meeting)'
        " || MEETING_I18N[lang] || MEETING_I18N.en;",
    ),
    (
        "default_extensions/ext-studio/panels/studio/view.js",
        "const dict = STUDIO_I18N[lang] || STUDIO_I18N.en;",
        'const dict = (lang === "es" && window.SERGIO_ES_EXT && window.SERGIO_ES_EXT.studio)'
        " || STUDIO_I18N[lang] || STUDIO_I18N.en;",
    ),
    # -- Meetings answer to «Sergio» too --------------------------------------
    (
        "default_extensions/meeting/panels/meeting/view.js",
        "    /@clacky\\b/i,\n",
        "    /@sergio\\b/i,\n    /\\b(hey|hola|oye|ok|okay|eh)[\\s,，]+sergio\\b/i,\n    /@clacky\\b/i,\n",
    ),
    (
        "default_extensions/meeting/panels/meeting/view.js",
        "    /@clacky/gi,\n",
        "    /@sergio/gi,\n    /\\b(hey|hola|oye|ok|okay|eh)[\\s,，]+sergio\\b/gi,\n    /@clacky/gi,\n",
    ),
    (
        "default_extensions/meeting/api/handler.rb",
        'SYSTEM_VOCABULARY = "Clacky, 小克".freeze',
        'SYSTEM_VOCABULARY = "Sergio, Clacky, 小克".freeze',
    ),
    (
        "default_extensions/meeting/api/handler.rb",
        'DEFAULT_VOCABULARY = "Clacky, 小克, OpenClacky, openclacky"',
        'DEFAULT_VOCABULARY = "Sergio, Clacky, 小克, OpenClacky, openclacky"',
    ),
    (
        "default_extensions/meeting/api/handler.rb",
        "question.match?(/\\A(open)?clacky\\z/i)",
        "question.match?(/\\A((open)?clacky|sergio)\\z/i)",
    ),
    # -- The built-in agents and panels, by their Spanish names --------------
    ("default_extensions/general/ext.yml", "      description: Handles your everyday work", "      description: Su trabajo de cada día"),
    ("default_extensions/coding/ext.yml", "      title: Coding\n", "      title: Código\n"),
    (
        "default_extensions/coding/ext.yml",
        "      description: Claude Code-grade coding capability, your technical co-founder",
        '      description: "Programa con usted: lee, escribe y prueba código"',
    ),
    ("default_extensions/ext-studio/ext.yml", "      title: Creator Center", "      title: Taller de extensiones"),
    (
        "default_extensions/ext-studio/ext.yml",
        "      description: Build, debug and publish extensions and skills",
        "      description: Crear, depurar y publicar extensiones y habilidades",
    ),
    ("default_extensions/ext-studio/ext.yml", "      title: Ext Developer", "      title: Extensiones"),
    (
        "default_extensions/ext-studio/ext.yml",
        "      description: AI expert that helps you build custom AI agent workflows",
        "      description: Le ayuda a crear flujos de trabajo con agentes propios",
    ),
    (
        "default_extensions/ext-studio/ext.yml",
        "description: AI-driven workspace for building, debugging, and publishing OpenClacky extensions",
        "description: Taller para crear, depurar y publicar extensiones del agente",
    ),
    ("default_extensions/ext-studio/panels/studio/view.js", '"nav.entry": "Creator Center"', '"nav.entry": "Taller de extensiones"'),
    ("default_extensions/ext-studio/panels/studio/view.js", '"ws.title": "Creator Center"', '"ws.title": "Taller de extensiones"'),
    ("default_extensions/advisor/ext.yml", "display_name: Advisor", "display_name: Sugerencias"),
    ("default_extensions/advisor/ext.yml", "      title: Advisor\n      title_zh: 工作建议\n      description: Recommends", "      title: Sugerencias\n      title_zh: 工作建议\n      description: Recommends"),
    ("default_extensions/advisor/ext.yml", "      title: Advisor\n      title_zh: 工作建议\n      description: Shows", "      title: Sugerencias\n      title_zh: 工作建议\n      description: Shows"),
    ("default_extensions/computer-use/ext.yml", "display_name: Computer Use", "display_name: Uso del ordenador"),
    ("default_extensions/git/ext.yml", "display_name: Git\n", "display_name: Cambios\n"),
    ("default_extensions/meeting/ext.yml", "display_name: Meeting", "display_name: Reuniones"),
    ("default_extensions/preview/ext.yml", "display_name: Preview", "display_name: Vista previa"),
    ("default_extensions/preview/ext.yml", "      title: Preview", "      title: Vista previa"),
    ("default_extensions/time_machine/ext.yml", "display_name: Time Machine", "display_name: Historial"),
]


# Files where a patch replaces every occurrence (the same line repeats).
EVERYWHERE = {"web/sessions.js", "web/features/tasks/store.js"}


def pending(patches: list[tuple[str, str, str]] = PATCHES, base: Path = AGENT) -> list[str]:
    """Patches not applied yet, as readable lines (empty when all are in)."""
    out = []
    for rel, old, new in patches:
        text = (base / rel).read_text(encoding="utf-8")
        if new not in text or old in text.replace(new, ""):
            out.append(f"{rel}: {old[:70]!r}")
    for name in OWN_FILES:
        if not (base / "web" / "sergio" / name).is_file():
            out.append(f"web/sergio/{name}: missing")
    return out


def apply(patches: list[tuple[str, str, str]] = PATCHES, base: Path = AGENT) -> int:
    """Apply every patch once; returns how many changed a file."""
    changed = 0
    for rel, old, new in patches:
        path = base / rel
        text = path.read_text(encoding="utf-8")
        if new in text and old not in text.replace(new, ""):
            continue
        if text.count(old) != 1 and rel not in EVERYWHERE:
            raise SystemExit(f"{rel}: the text to patch is not there exactly once: {old[:70]!r}")
        if not text.count(old):
            raise SystemExit(f"{rel}: the text to patch is not there: {old[:70]!r}")
        path.write_text(text.replace(old, new), encoding="utf-8")
        changed += 1
    return changed


def main(argv: list[str]) -> int:
    if "--check" in argv:
        left = pending()
        for line in left:
            print("sin aplicar:", line)
        return 1 if left else 0
    n = apply()
    left = pending()
    print(f"Parche de marca del agente: {n} cambios aplicados, {len(left)} pendientes.")
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
