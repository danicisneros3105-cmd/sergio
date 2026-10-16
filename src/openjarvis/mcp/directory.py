"""The connector directory: remote MCP servers one click away, as in Claude.

URLs come from the official plugin marketplaces (``.mcp.json`` of
anthropics/knowledge-work-plugins and anthropics/claude-plugins-official,
October 2026) and the services' own help pages. Endpoints hosted by
Anthropic for Claude only, or built for Claude's own OAuth client, are left
out on purpose. ``local`` entries run on the owner's PC (stdio), like
Claude's desktop extensions. Names are shown as plain text, no logos.
"""

from __future__ import annotations

from typing import Any, Dict, List

CATEGORIES = [
    "Destacados",
    "Productividad",
    "Comunicación",
    "Diseño y creación",
    "Desarrollo",
    "Datos y análisis",
    "Ventas y clientes",
    "Finanzas",
    "Ciencia",
    "En su PC",
]


def _r(
    id: str,
    name: str,
    url: str,
    cat: str,
    what: str,
    *,
    featured: bool = False,
    note: str = "",
) -> Dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "kind": "remote",
        "url": url,
        "category": cat,
        "description": what,
        "featured": featured,
        "note": note,
    }


def _l(
    id: str,
    name: str,
    command: List[str],
    what: str,
    *,
    needs: str = "",
    args_hint: str = "",
) -> Dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "kind": "local",
        "command": command,
        "category": "En su PC",
        "description": what,
        "featured": False,
        "needs": needs,
        "args_hint": args_hint,
        "note": "",
    }


DIRECTORY: List[Dict[str, Any]] = [
    # -- the owner's own picks first -----------------------------------------
    _r(
        "gmail",
        "Gmail",
        "https://gmailmcp.googleapis.com/mcp/v1",
        "Comunicación",
        "Busca y lee correos, prepara borradores y ordena etiquetas.",
        featured=True,
        note="Servidor oficial de Google, en vista previa: pide un Client ID propio de Google Cloud "
        "(Opciones avanzadas). Solo crea borradores; enviar sigue siendo cosa suya.",
    ),
    _r(
        "notion",
        "Notion",
        "https://mcp.notion.com/mcp",
        "Productividad",
        "Busca, lee y edita páginas y bases de datos de su espacio.",
        featured=True,
    ),
    _r(
        "higgsfield",
        "Higgsfield",
        "https://mcp.higgsfield.ai/mcp",
        "Diseño y creación",
        "Genera imágenes y videos con sus créditos de Higgsfield.",
        featured=True,
        note="Necesita una suscripción de pago de Higgsfield.",
    ),
    _r(
        "google-calendar",
        "Google Calendar",
        "https://calendarmcp.googleapis.com/mcp/v1",
        "Productividad",
        "Consulta y prepara eventos de su calendario.",
        featured=True,
        note="Servidor oficial de Google: pide un Client ID propio de Google Cloud.",
    ),
    _r(
        "google-drive",
        "Google Drive",
        "https://drivemcp.googleapis.com/mcp/v1",
        "Productividad",
        "Busca y lee documentos de su Drive.",
        note="Servidor oficial de Google: pide un Client ID propio de Google Cloud.",
    ),
    _r(
        "github",
        "GitHub",
        "https://api.githubcopilot.com/mcp/",
        "Desarrollo",
        "Repositorios, issues, pull requests y revisiones.",
        featured=True,
    ),
    _r(
        "canva",
        "Canva",
        "https://mcp.canva.com/mcp",
        "Diseño y creación",
        "Crea y edita diseños de su cuenta.",
        featured=True,
    ),
    _r(
        "figma",
        "Figma",
        "https://mcp.figma.com/mcp",
        "Diseño y creación",
        "Lee archivos y componentes de diseño.",
        featured=True,
    ),
    _r(
        "slack",
        "Slack",
        "https://mcp.slack.com/mcp",
        "Comunicación",
        "Canales, mensajes y búsqueda.",
        note="Slack no deja registrarse solo: pide un Client ID de una app de Slack suya.",
    ),
    _r(
        "linear",
        "Linear",
        "https://mcp.linear.app/mcp",
        "Productividad",
        "Tareas, proyectos y ciclos.",
    ),
    _r(
        "asana",
        "Asana",
        "https://mcp.asana.com/v2/mcp",
        "Productividad",
        "Tareas y proyectos del equipo.",
    ),
    _r(
        "atlassian",
        "Jira y Confluence",
        "https://mcp.atlassian.com/v1/mcp",
        "Productividad",
        "Incidencias de Jira y páginas de Confluence.",
    ),
    _r(
        "monday",
        "monday.com",
        "https://mcp.monday.com/mcp",
        "Productividad",
        "Tableros y elementos de trabajo.",
    ),
    _r(
        "clickup",
        "ClickUp",
        "https://mcp.clickup.com/mcp",
        "Productividad",
        "Tareas, documentos y espacios.",
    ),
    _r(
        "trello",
        "Trello",
        "https://mcp.trello.com/v1",
        "Productividad",
        "Tableros, listas y tarjetas.",
    ),
    _r(
        "box",
        "Box",
        "https://mcp.box.com",
        "Productividad",
        "Archivos y carpetas de Box.",
    ),
    _r(
        "egnyte",
        "Egnyte",
        "https://mcp-server.egnyte.com/mcp",
        "Productividad",
        "Archivos de la empresa.",
    ),
    _r(
        "granola",
        "Granola",
        "https://mcp.granola.ai/mcp",
        "Comunicación",
        "Notas de sus reuniones.",
    ),
    _r(
        "otter",
        "Otter.ai",
        "https://mcp.otter.ai/mcp",
        "Comunicación",
        "Transcripciones de reuniones.",
    ),
    _r(
        "fireflies",
        "Fireflies",
        "https://api.fireflies.ai/mcp",
        "Comunicación",
        "Grabaciones y resúmenes de reuniones.",
    ),
    _r(
        "zoom",
        "Zoom",
        "https://mcp.zoom.us/mcp/zoom/streamable",
        "Comunicación",
        "Reuniones y grabaciones.",
    ),
    _r(
        "intercom",
        "Intercom",
        "https://mcp.intercom.com/mcp",
        "Ventas y clientes",
        "Conversaciones con clientes.",
    ),
    _r(
        "calendly",
        "Calendly",
        "https://mcp.calendly.com/",
        "Productividad",
        "Citas y disponibilidad.",
    ),
    _r(
        "docusign",
        "Docusign",
        "https://mcp.docusign.com/mcp",
        "Productividad",
        "Sobres y firmas.",
    ),
    _r(
        "wix",
        "Wix",
        "https://mcp.wix.com/mcp",
        "Diseño y creación",
        "Sitios, tiendas y contenido.",
    ),
    _r(
        "biorender",
        "BioRender",
        "https://mcp.services.biorender.com/mcp",
        "Diseño y creación",
        "Figuras científicas e iconos.",
    ),
    _r(
        "gitlab",
        "GitLab",
        "https://gitlab.com/api/v4/mcp",
        "Desarrollo",
        "Proyectos, issues y merge requests.",
    ),
    _r(
        "pagerduty",
        "PagerDuty",
        "https://mcp.pagerduty.com/mcp",
        "Desarrollo",
        "Incidentes y guardias.",
    ),
    _r(
        "datadog",
        "Datadog",
        "https://mcp.datadoghq.com/api/unstable/mcp-server/mcp",
        "Desarrollo",
        "Métricas, registros y alertas.",
    ),
    _r(
        "sentry",
        "Sentry",
        "https://mcp.sentry.dev/mcp",
        "Desarrollo",
        "Errores y rendimiento de sus apps.",
    ),
    _r(
        "context7",
        "Context7",
        "https://mcp.context7.com/mcp",
        "Desarrollo",
        "Documentación al día de librerías de código.",
    ),
    _r(
        "emergent",
        "Emergent",
        "https://mcp.emergent.sh",
        "Desarrollo",
        "Crea apps conversando.",
    ),
    _r(
        "bigquery",
        "BigQuery",
        "https://bigquery.googleapis.com/mcp",
        "Datos y análisis",
        "Consultas sobre sus datos de Google Cloud.",
        note="Servidor oficial de Google: pide un Client ID propio de Google Cloud.",
    ),
    _r(
        "amplitude",
        "Amplitude",
        "https://mcp.amplitude.com/mcp",
        "Datos y análisis",
        "Analítica de producto.",
    ),
    _r(
        "hex",
        "Hex",
        "https://app.hex.tech/mcp",
        "Datos y análisis",
        "Cuadernos y análisis de datos.",
    ),
    _r(
        "definite",
        "Definite",
        "https://api.definite.app/v3/mcp/http",
        "Datos y análisis",
        "Datos del negocio.",
    ),
    _r(
        "similarweb",
        "Similarweb",
        "https://mcp.similarweb.com/mcp",
        "Datos y análisis",
        "Tráfico de sitios web.",
    ),
    _r(
        "ahrefs",
        "Ahrefs",
        "https://api.ahrefs.com/mcp/mcp",
        "Datos y análisis",
        "SEO y enlaces.",
    ),
    _r(
        "supermetrics",
        "Supermetrics",
        "https://mcp.supermetrics.com/mcp",
        "Datos y análisis",
        "Datos de marketing en un solo sitio.",
    ),
    _r(
        "klaviyo",
        "Klaviyo",
        "https://mcp.klaviyo.com/mcp",
        "Ventas y clientes",
        "Campañas de correo y SMS.",
    ),
    _r(
        "apollo",
        "Apollo",
        "https://mcp.apollo.io/mcp",
        "Ventas y clientes",
        "Prospección de ventas.",
    ),
    _r(
        "close",
        "Close",
        "https://mcp.close.com/mcp",
        "Ventas y clientes",
        "CRM de ventas.",
    ),
    _r(
        "gong",
        "Gong",
        "https://mcp.gong.io/mcp",
        "Ventas y clientes",
        "Llamadas y oportunidades.",
    ),
    _r(
        "outreach",
        "Outreach",
        "https://api.outreach.io/mcp/",
        "Ventas y clientes",
        "Secuencias de ventas.",
    ),
    _r(
        "clay",
        "Clay",
        "https://api.clay.com/v3/mcp",
        "Ventas y clientes",
        "Enriquecimiento de contactos.",
    ),
    _r(
        "common-room",
        "Common Room",
        "https://mcp.commonroom.io/mcp",
        "Ventas y clientes",
        "Señales de la comunidad.",
    ),
    _r(
        "crunchbase",
        "Crunchbase",
        "https://mcp.crunchbase.com/",
        "Ventas y clientes",
        "Empresas e inversiones.",
    ),
    _r(
        "zoominfo",
        "ZoomInfo",
        "https://mcp.zoominfo.com/mcp",
        "Ventas y clientes",
        "Datos de empresas y contactos.",
    ),
    _r(
        "shopify",
        "Shopify",
        "https://setup.shopify.com/mcp",
        "Ventas y clientes",
        "Su tienda: productos y pedidos.",
    ),
    _r(
        "tiktok-ads",
        "TikTok Ads",
        "https://business-api.tiktok.com/open_mcp/tt-ads-mcp-layer",
        "Ventas y clientes",
        "Campañas de anuncios.",
    ),
    _r(
        "stripe",
        "Stripe",
        "https://mcp.stripe.com",
        "Finanzas",
        "Pagos, clientes y suscripciones.",
    ),
    _r(
        "paypal",
        "PayPal",
        "https://mcp.paypal.com/mcp",
        "Finanzas",
        "Pagos y facturas.",
    ),
    _r(
        "square",
        "Square",
        "https://mcp.squareup.com/mcp",
        "Finanzas",
        "Ventas y catálogo.",
    ),
    _r(
        "ramp",
        "Ramp",
        "https://mcp.ramp.com/mcp",
        "Finanzas",
        "Gastos y tarjetas de empresa.",
    ),
    _r("xero", "Xero", "https://mcp.xero.com/mcp", "Finanzas", "Contabilidad."),
    _r(
        "quickbooks",
        "QuickBooks",
        "https://ai-inc.quickbooks.intuit.com/v1/mcp",
        "Finanzas",
        "Contabilidad.",
    ),
    _r(
        "expensify",
        "Expensify",
        "https://www.expensify.com/mcp",
        "Finanzas",
        "Gastos e informes.",
    ),
    _r(
        "airwallex",
        "Airwallex",
        "https://mcp.airwallex.com/mcp",
        "Finanzas",
        "Pagos internacionales.",
    ),
    _r("myob", "MYOB", "https://mcp.myob.com/mcp", "Finanzas", "Contabilidad."),
    _r(
        "consensus",
        "Consensus",
        "https://mcp.consensus.app/mcp",
        "Ciencia",
        "Busca en artículos científicos.",
    ),
    _r(
        "open-targets",
        "Open Targets",
        "https://mcp.platform.opentargets.org/mcp",
        "Ciencia",
        "Dianas de fármacos y enfermedades.",
    ),
    _r(
        "synapse",
        "Synapse",
        "https://mcp.synapse.org/mcp",
        "Ciencia",
        "Datos de investigación biomédica.",
    ),
    _r(
        "scholar-gateway",
        "Scholar Gateway",
        "https://connector.scholargateway.ai/mcp",
        "Ciencia",
        "Literatura académica.",
    ),
    _r(
        "zapier",
        "Zapier",
        "https://mcp.zapier.com/api/v1/connect",
        "Productividad",
        "Miles de apps a través de sus Zaps.",
    ),
    _r(
        "hugging-face",
        "Hugging Face",
        "https://huggingface.co/mcp",
        "Desarrollo",
        "Modelos, datasets y Spaces.",
    ),
    # -- on the PC (stdio), like Claude's desktop extensions ------------------
    _l(
        "archivos",
        "Archivos",
        ["npx", "-y", "@modelcontextprotocol/server-filesystem"],
        "Lee y escribe en las carpetas que usted elija.",
        needs="Node.js",
        args_hint="Carpetas permitidas",
    ),
    _l(
        "navegador",
        "Navegador",
        ["npx", "-y", "@playwright/mcp@latest"],
        "Abre páginas, hace clic y rellena formularios.",
        needs="Node.js",
    ),
    _l(
        "memoria",
        "Memoria de grafo",
        ["npx", "-y", "@modelcontextprotocol/server-memory"],
        "Un grafo de conocimiento que persiste entre conversaciones.",
        needs="Node.js",
    ),
    _l(
        "paginas",
        "Leer páginas",
        ["uvx", "mcp-server-fetch"],
        "Descarga páginas web y las pasa a texto.",
        needs="uv",
    ),
    _l(
        "git",
        "Git",
        ["uvx", "mcp-server-git"],
        "Historial, diferencias y commits de un repositorio.",
        needs="uv",
        args_hint="--repository <carpeta>",
    ),
    _l(
        "blender",
        "Blender",
        ["uvx", "blender-mcp"],
        "Controla Blender abierto en su PC.",
        needs="uv y Blender",
    ),
    _l(
        "escritorio",
        "Terminal y archivos",
        ["npx", "-y", "@wonderwhy-er/desktop-commander"],
        "Ejecuta órdenes y edita archivos en su PC (con su permiso).",
        needs="Node.js",
    ),
]


# Supported scopes are a menu. Request only what this integration uses.
_SETUP = {
    "gmail": {
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose"],
        "setup_url": "https://developers.google.com/workspace/guides/configure-mcp-servers",
        "requires_client_id": True,
        "note": "Requiere Google Workspace Developer Preview, APIs habilitadas y Client ID/Secret de Google Cloud. Registre la URL de retorno de Sergio y marque el cliente como agente de IA. Solo borradores.",
    },
    "google-calendar": {
        "scopes": ["https://www.googleapis.com/auth/calendar.calendarlist.readonly", "https://www.googleapis.com/auth/calendar.events.readonly"],
        "setup_url": "https://developers.google.com/workspace/guides/configure-mcp-servers",
        "requires_client_id": True,
    },
    "google-drive": {
        "scopes": ["https://www.googleapis.com/auth/drive.readonly"],
        "setup_url": "https://developers.google.com/workspace/guides/configure-mcp-servers",
        "requires_client_id": True,
    },
    "notion": {"setup_url": "https://developers.notion.com/guides/mcp/get-started-with-mcp"},
    "higgsfield": {"setup_url": "https://higgsfield.ai/creator-hub/help-center/integrations/how-do-i-connect-higgsfield-to-ai-agent"},
}
for _entry in DIRECTORY:
    _entry.update(_SETUP.get(_entry["id"], {}))


def directory() -> List[Dict[str, Any]]:
    return [dict(entry) for entry in DIRECTORY]


def find(entry_id: str) -> Dict[str, Any]:
    for entry in DIRECTORY:
        if entry["id"] == entry_id:
            return dict(entry)
    raise KeyError(entry_id)


__all__ = ["CATEGORIES", "DIRECTORY", "directory", "find"]
