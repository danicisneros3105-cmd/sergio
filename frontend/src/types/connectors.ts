export interface SetupStep {
  label: string;
  url?: string;
  urlLabel?: string;
}

export interface ConnectorMeta {
  connector_id: string;
  display_name: string;
  auth_type: 'oauth' | 'local' | 'bridge' | 'filesystem' | 'token';
  category: 'communication' | 'documentos' | 'pim' | 'other';
  icon: string;
  color: string;
  description: string;
  unitLabel?: string;  // "emails", "messages", "meeting notes", "pages", "notes", etc.
  steps?: SetupStep[];
  troubleshooting?: string[];
  inputFields?: Array<{
    name: string;
    placeholder: string;
    type?: 'text' | 'password' | 'number' | 'select';
    required?: boolean;
    defaultValue?: string;
    options?: Array<{ value: string; label: string }>;
  }>;
}

export interface OAuthSetupInfo {
  provider: string;
  setup_url: string;
  setup_hint: string;
  has_credentials: boolean;
}

export interface ConnectorInfo {
  connector_id: string;
  display_name: string;
  auth_type: "oauth" | "local" | "bridge" | "filesystem" | "token";
  connected: boolean;
  auth_url?: string;
  mcp_tools?: string[];
  chunks?: number;
  oauth_setup?: OAuthSetupInfo | null;
}

export interface SyncStatus {
  state: "idle" | "syncing" | "stopping" | "paused" | "error";
  items_synced: number;
  items_total: number;
  /** Items processed in the current (or most recent) run only. `null`
   *  when no sync has been triggered through this server session yet. */
  new_items_synced?: number | null;
  /** ISO 8601 timestamp of the oldest indexed item, used to label how far
   *  back the corpus reaches ("past 3 months", "past 5 years"). `null`
   *  before anything is indexed. */
  oldest_item_date?: string | null;
  last_sync: string | null;
  error: string | null;
}

export interface ConnectRequest {
  path?: string;
  token?: string;
  code?: string;
  email?: string;
  password?: string;
  /** Non-secret connector configuration such as a weather location or RSS feeds. */
  config?: Record<string, unknown>;
  host?: string;
  port?: number;
  security?: 'tls' | 'starttls';
}

/** Response from POST /v1/connectors/{id}/connect.
 *  For OAuth connectors, pasting a Client ID / Secret pair only registers the
 *  app credentials; the backend returns `status: "oauth_required"` plus an
 *  `oauth_start` path the UI must open to run the browser consent flow that
 *  actually mints an access token (see issue #512). */
export interface ConnectResponse {
  connector_id: string;
  connected: boolean;
  status: "connected" | "pending" | "oauth_required" | "disconnected";
  oauth_start?: string;
  sync_status?: string | null;
}

export type WizardStep = "pick" | "connect" | "ingest" | "ready";

// Backward-compatible alias
export type SourceCard = ConnectorMeta;

export type ConnectorCategory = ConnectorMeta['category'];

export const SOURCE_CATALOG: ConnectorMeta[] = [
  // ── Subir o pegar ─────────────────────────────────────────────────
  {
    connector_id: 'upload',
    display_name: 'Subir o pegar',
    auth_type: 'filesystem',
    category: 'other',
    icon: 'FileUp',
    color: 'text-blue-400',
    description: 'Pegar texto o subir documentos',
    unitLabel: 'documentos',
    steps: [
      { label: 'Pegue texto o suba archivos (.txt, .md, .pdf, .docx, .csv) para agregarlos a la memoria.' },
    ],
    inputFields: [],
  },
  // ── Communication ──────────────────────────────────────────────────
  {
    // Unified Gmail card. Defaults to the IMAP (app-password) flow because
    // it needs no Google Cloud setup; the OAuth path is offered as an
    // "Advanced" disclosure rendered in DataSourcesPage.
    connector_id: 'gmail_imap',
    display_name: 'Gmail',
    auth_type: 'oauth',
    category: 'communication',
    icon: 'Mail',
    color: 'text-red-400',
    description: 'Correos y conversaciones',
    unitLabel: 'correos',
    steps: [
      {
        label: 'Active la verificación en dos pasos y genere una contraseña de aplicación de 16 caracteres (Correo / Otro / «Sergio»). Péguela abajo \u2014 los espacios no importan \u2014 y use esa contraseña, no la normal de Gmail.',
        url: 'https://myaccount.google.com/apppasswords',
        urlLabel: 'Cómo obtener una contraseña de aplicación \u2192',
      },
    ],
    troubleshooting: [
      "Don't see App Passwords? Make sure 2-Step Verification is enabled first.",
      "Google Workspace user? Your admin may need to enable App Passwords for your organization.",
    ],
    inputFields: [
      { name: 'email', placeholder: 'usted@gmail.com', type: 'text' },
      { name: 'password', placeholder: 'Contraseña de aplicación (xxxx xxxx xxxx xxxx)', type: 'password' },
    ],
  },
  {
    connector_id: 'imap',
    display_name: 'Email (IMAP)',
    auth_type: 'oauth',
    category: 'communication',
    icon: 'Mail',
    color: 'text-amber-400',
    description: 'Cualquier buzón IMAP',
    unitLabel: 'correos',
    steps: [
      {
        label: 'Genere una contraseña de aplicación con su proveedor de correo (IMAP debe estar activo), luego escriba su correo y esa contraseña. Los proveedores conocidos se detectan solos; para otros use los datos opcionales del servidor.',
      },
    ],
    troubleshooting: [
      'La mayoría de los proveedores piden una contraseña de aplicación, no la normal.',
      'Use TLS (normalmente puerto 993) o STARTTLS (normalmente puerto 143).',
      'Por seguridad se rechazan las direcciones de servidor privadas, locales o no públicas.',
    ],
    inputFields: [
      { name: 'email', placeholder: 'usted@ejemplo.com', type: 'text' },
      { name: 'password', placeholder: 'Contraseña de aplicación', type: 'password' },
      {
        name: 'host',
        placeholder: 'Servidor IMAP (opcional; se detecta solo)',
        type: 'text',
        required: false,
      },
      {
        name: 'port',
        placeholder: 'Puerto (opcional; 993 o 143)',
        type: 'number',
        required: false,
      },
      {
        name: 'security',
        placeholder: 'Seguridad de la conexión',
        type: 'select',
        defaultValue: 'tls',
        options: [
          { value: 'tls', label: 'TLS (normalmente puerto 993)' },
          { value: 'starttls', label: 'STARTTLS (normalmente puerto 143)' },
        ],
      },
    ],
  },
  {
    connector_id: 'slack',
    display_name: 'Slack',
    auth_type: 'oauth',
    category: 'communication',
    icon: 'Hash',
    color: 'text-purple-400',
    description: 'Lee los mensajes de todos los canales, canales privados y mensajes directos a los que usted tiene acceso',
    unitLabel: 'mensajes',
    steps: [
      {
        label: 'Entre a api.slack.com/apps y pulse «Create New App» → elija «From scratch». Llámela «Sergio» y escoja su espacio de trabajo',
        url: 'https://api.slack.com/apps',
        urlLabel: 'Abrir Slack Apps',
      },
      {
        label: 'En la barra izquierda pulse «OAuth & Permissions». Baje a «User Token Scopes» (NO a «Bot Token Scopes»). Pulse «Add an OAuth Scope» y agregue UNO POR UNO estos permisos:',
      },
      {
        label: 'channels:history • channels:read • groups:history • groups:read • im:history • im:read • mpim:history • mpim:read • users:read',
      },
      {
        label: 'En la barra izquierda pulse «Install App» → «Install to Workspace» → «Allow». Después copie el «User OAuth Token» que aparece (empieza con xoxp-, NO con xoxb-)',
      },
      {
        label: 'Pegue abajo el token de usuario. La sincronización indexa todos los canales, canales privados y mensajes directos a los que tiene acceso; no hace falta invitar a nadie',
      },
    ],
    inputFields: [
      { name: 'token', placeholder: 'xoxp-...', type: 'password' },
    ],
  },
  {
    connector_id: 'notion',
    display_name: 'Notion',
    auth_type: 'oauth',
    category: 'documentos',
    icon: 'FileText',
    color: 'text-gray-300',
    description: 'Páginas y bases de datos',
    unitLabel: 'páginas',
    steps: [
      {
        label: 'Entre a notion.so/profile/integrations → pulse «+ New integration». Llámela «Sergio», elija su espacio de trabajo y pulse Submit',
        url: 'https://www.notion.so/profile/integrations',
        urlLabel: 'Abrir integraciones de Notion',
      },
      {
        label: 'Copie el «Internal Integration Secret» (empieza con ntn_) y péguelo abajo',
      },
      {
        label: 'Para compartir TODAS sus páginas: abra una página principal → pulse «...» (arriba a la derecha) → «Connections» → «Add connections» → busque «Sergio» y púlselo. Así se comparte la página y sus subpáginas. Repita con cada página principal',
      },
      {
        label: 'Consejo: si una sola página principal contiene todo, compartir solo esa página comparte automáticamente todas las subpáginas',
      },
    ],
    inputFields: [
      { name: 'token', placeholder: 'ntn_...', type: 'password' },
    ],
  },
  {
    connector_id: 'granola',
    display_name: 'Granola',
    auth_type: 'oauth',
    category: 'documentos',
    icon: 'Mic',
    color: 'text-amber-400',
    description: 'Notas de reuniones con IA',
    unitLabel: 'notas de reunión',
    steps: [
      { label: 'Abra la aplicación de escritorio de Granola. Pulse el engranaje (Ajustes) abajo a la izquierda y luego «API»' },
      { label: 'Pulse «Generate API Key» (o copie la que ya tiene). Pegue la clave abajo' },
    ],
    inputFields: [
      { name: 'token', placeholder: 'grn_...', type: 'password' },
    ],
  },
  {
    connector_id: 'imessage',
    display_name: 'iMessage',
    auth_type: 'local',
    category: 'communication',
    icon: 'MessageSquare',
    color: 'text-green-400',
    description: 'Historial de Mensajes de macOS',
    unitLabel: 'mensajes',
    steps: [
      {
        label: 'Abra el menú de Apple () → Ajustes del Sistema → Privacidad y seguridad (barra izquierda) → baje y pulse «Acceso total al disco»',
      },
      {
        label: 'Pulse el botón «+» al final de la lista. Vaya a Aplicaciones → Utilidades → elija «Terminal.app» (o iTerm2/Warp si los usa). Si usa la aplicación de escritorio, agregue también «Sergio.app» desde Aplicaciones',
      },
      {
        label: 'Active el interruptor de cada aplicación que agregó. Cierre y vuelva a abrir la terminal (o reinicie Sergio). Los datos de iMessage se detectan solos; no hacen falta credenciales',
      },
    ],
  },
  // ── Documents ──────────────────────────────────────────────────────
  {
    connector_id: 'obsidian',
    display_name: 'Obsidian',
    auth_type: 'filesystem',
    category: 'documentos',
    icon: 'FolderOpen',
    color: 'text-purple-300',
    description: 'Bóveda de Markdown',
    unitLabel: 'notas',
    steps: [
      {
        label: 'Busque la ruta de su bóveda: abra Obsidian → pulse el nombre de la bóveda abajo a la izquierda → «Manage Vaults» → mire la ruta bajo el nombre. En macOS suele ser ~/Documents/MyVault o ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/MyVault',
      },
      {
        label: 'También puede abrir Finder → ir a la carpeta de su bóveda (tiene una carpeta oculta .obsidian) → clic derecho → «Copy as Pathname» para obtener la ruta completa',
      },
      {
        label: 'Pegue abajo la ruta completa. Sergio indexará todos los archivos .md de la bóveda',
      },
    ],
    inputFields: [
      { name: 'path', placeholder: '/Users/usted/Documents/MyVault', type: 'text' },
    ],
  },
  {
    connector_id: 'gdrive',
    display_name: 'Google Drive',
    auth_type: 'oauth',
    category: 'documentos',
    icon: 'FolderOpen',
    color: 'text-blue-400',
    description: 'Documentos, hojas de cálculo y archivos',
    unitLabel: 'archivos',
    steps: [
      {
        label: 'Entre a Google Cloud Console → cree un proyecto nuevo (o elija uno existente). Póngale cualquier nombre (por ejemplo «Sergio»)',
        url: 'https://console.cloud.google.com/projectcreate',
        urlLabel: 'Crear proyecto',
      },
      {
        label: 'Active la API de Google Drive: pulse el enlace de abajo, compruebe que su proyecto está elegido arriba y pulse «Enable»',
        url: 'https://console.cloud.google.com/apis/library/drive.googleapis.com',
        urlLabel: 'Activar API de Drive',
      },
      {
        label: 'Cree las credenciales OAuth: vaya a Credentials (enlace de abajo) → «+ Create Credentials» → «OAuth client ID» → tipo de aplicación «Web application». En «Authorized redirect URIs» agregue la dirección de retorno de este servidor (por ejemplo http://localhost:1313/v1/connectors/gdrive/oauth/callback; use el mismo equipo y puerto donde corre Sergio) → «Create».',
        url: 'https://console.cloud.google.com/apis/credentials',
        urlLabel: 'Abrir credenciales',
      },
      {
        label: 'Una ventana mostrará su Client ID y su Client Secret. Copie los dos y péguelos abajo, luego pulse Conectar: se abre una ventana de Google para terminar la autorización. (Si cierra la ventana, pulse el icono de descarga junto a su cliente OAuth para verlos otra vez.)',
      },
    ],
    inputFields: [
      { name: 'email', placeholder: 'Client ID (por ejemplo 123456-abc.apps.googleusercontent.com)', type: 'text' },
      { name: 'password', placeholder: 'Client Secret', type: 'password' },
    ],
  },
  // ── PIM (Calendar, Contacts) ───────────────────────────────────────
  {
    connector_id: 'gcalendar',
    display_name: 'Google Calendar',
    auth_type: 'oauth',
    category: 'pim',
    icon: 'Calendar',
    color: 'text-blue-400',
    description: 'Eventos y reuniones',
    unitLabel: 'eventos',
    steps: [
      {
        label: 'Entre a Google Cloud Console → use el mismo proyecto de Google Drive (o cree uno nuevo)',
        url: 'https://console.cloud.google.com/projectcreate',
        urlLabel: 'Abrir la consola',
      },
      {
        label: 'Active la API de Google Calendar: pulse el enlace de abajo, elija su proyecto y pulse «Enable»',
        url: 'https://console.cloud.google.com/apis/library/calendar-json.googleapis.com',
        urlLabel: 'Activar API de Calendar',
      },
      {
        label: 'Vaya a Credentials → «+ Create Credentials» → «OAuth client ID» → tipo «Desktop app» → «Create». Copie el Client ID y el Client Secret',
        url: 'https://console.cloud.google.com/apis/credentials',
        urlLabel: 'Abrir credenciales',
      },
      {
        label: 'Pegue abajo el Client ID y el Client Secret (puede reutilizar el mismo cliente OAuth de Google Drive si activó las dos API en el mismo proyecto)',
      },
    ],
    inputFields: [
      { name: 'email', placeholder: 'Client ID', type: 'text' },
      { name: 'password', placeholder: 'Client Secret', type: 'password' },
    ],
  },
  {
    connector_id: 'gcontacts',
    display_name: 'Google Contacts',
    auth_type: 'oauth',
    category: 'pim',
    icon: 'Users',
    color: 'text-blue-400',
    description: 'Personas y datos de contacto',
    unitLabel: 'contactos',
    steps: [
      {
        label: 'Entre a Google Cloud Console → use el mismo proyecto de Google Drive (o cree uno nuevo)',
        url: 'https://console.cloud.google.com/projectcreate',
        urlLabel: 'Abrir la consola',
      },
      {
        label: 'Active la API de People: pulse el enlace de abajo, elija su proyecto y pulse «Enable»',
        url: 'https://console.cloud.google.com/apis/library/people.googleapis.com',
        urlLabel: 'Activar API de People',
      },
      {
        label: 'Vaya a Credentials → «+ Create Credentials» → «OAuth client ID» → tipo «Desktop app» → «Create». Copie el Client ID y el Client Secret',
        url: 'https://console.cloud.google.com/apis/credentials',
        urlLabel: 'Abrir credenciales',
      },
      {
        label: 'Pegue abajo el Client ID y el Client Secret',
      },
    ],
    inputFields: [
      { name: 'email', placeholder: 'Client ID', type: 'text' },
      { name: 'password', placeholder: 'Client Secret', type: 'password' },
    ],
  },
  {
    connector_id: 'apple_notes',
    display_name: 'Apple Notes',
    auth_type: 'local',
    category: 'documentos',
    icon: 'FileText',
    color: 'text-yellow-400',
    description: 'Aplicación Notas de macOS',
    unitLabel: 'notas',
    steps: [
      {
        label: 'Abra el menú de Apple () → Ajustes del Sistema → Privacidad y seguridad (barra izquierda) → baje y pulse «Acceso total al disco»',
      },
      {
        label: 'Pulse el botón «+» al final de la lista. Vaya a Aplicaciones → Utilidades → elija «Terminal.app» (o iTerm2/Warp si los usa). Si usa la aplicación de escritorio, agregue también «Sergio.app» desde Aplicaciones',
      },
      {
        label: 'Active el interruptor de cada aplicación que agregó. Cierre y vuelva a abrir la terminal (o reinicie Sergio). Notas de Apple se detecta sola; no hacen falta credenciales',
      },
    ],
  },
  {
    connector_id: 'apple_contacts',
    display_name: 'Apple Contacts',
    auth_type: 'local',
    category: 'pim',
    icon: 'Users',
    color: 'text-orange-400',
    description: 'Aplicación Contactos de macOS',
    unitLabel: 'contactos',
    steps: [
      {
        label: 'Abra el menú de Apple () → Ajustes del Sistema → Privacidad y seguridad (barra izquierda) → baje y pulse «Acceso total al disco»',
      },
      {
        label: 'Pulse el botón «+» al final de la lista. Vaya a Aplicaciones → Utilidades → elija «Terminal.app» (o iTerm2/Warp si los usa). Si usa la aplicación de escritorio, agregue también «Sergio.app» desde Aplicaciones',
      },
      {
        label: 'Active el interruptor de cada aplicación que agregó. Cierre y vuelva a abrir la terminal (o reinicie Sergio). Contactos de Apple se detecta solo; no hacen falta credenciales',
      },
    ],
  },
  {
    connector_id: 'outlook',
    display_name: 'Outlook',
    auth_type: 'oauth',
    category: 'communication',
    icon: 'Mail',
    color: 'text-blue-400',
    description: 'Correo y calendario de Microsoft',
    unitLabel: 'correos',
    steps: [
      {
        label: 'Entre a Azure Portal → App Registrations → «+ New registration». Llámela «Sergio», elija «Accounts in this organizational directory only» y pulse Register',
        url: 'https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade',
        urlLabel: 'Abrir registros de aplicaciones de Azure',
      },
      {
        label: 'En la barra izquierda pulse «API Permissions» → «Add a permission» → «Microsoft Graph» → «Delegated permissions» → busque y marque «Mail.Read» → «Add permissions»',
      },
      {
        label: 'En la barra izquierda pulse «Certificates & secrets» → «New client secret» → ponga una descripción y una caducidad → «Add» → copie enseguida el «Value» (no volverá a verlo)',
      },
      {
        label: 'Vaya a «Overview» en la barra izquierda y copie el «Application (client) ID». Pegue abajo el Client ID y el Client Secret',
      },
    ],
    inputFields: [
      { name: 'email', placeholder: 'Application (client) ID', type: 'text' },
      { name: 'password', placeholder: 'Client Secret Value', type: 'password' },
    ],
  },
  {
    connector_id: 'dropbox',
    display_name: 'Dropbox',
    auth_type: 'oauth',
    category: 'documentos',
    icon: 'FolderOpen',
    color: 'text-blue-300',
    description: 'Almacenamiento de archivos en la nube',
    unitLabel: 'archivos',
    steps: [
      {
        label: 'Entre a Dropbox App Console y pulse «Create app». Elija «Scoped access» → «Full Dropbox» → póngale un nombre (por ejemplo «Sergio») → «Create app»',
        url: 'https://www.dropbox.com/developers/apps/create',
        urlLabel: 'Abrir la consola de Dropbox',
      },
      {
        label: 'Pulse la pestaña «Permissions» arriba. Marque «files.metadata.read» y «files.content.read» → pulse «Submit» abajo para guardar',
      },
      {
        label: 'Vuelva a la pestaña «Settings». En «OAuth 2» busque «Generated access token» y pulse «Generate». Copie el token y péguelo abajo',
      },
    ],
    inputFields: [
      { name: 'token', placeholder: 'Token de acceso (sl.u...)', type: 'password' },
    ],
  },
  {
    connector_id: 'whatsapp',
    display_name: 'WhatsApp',
    auth_type: 'oauth',
    category: 'communication',
    icon: 'MessageSquare',
    color: 'text-green-400',
    description: 'Mensajes de WhatsApp (API oficial de Meta)',
    unitLabel: 'mensajes',
    steps: [
      {
        label: 'Entre a Meta for Developers → «Create App» → tipo «Business» → complete los datos y pulse «Create App»',
        url: 'https://developers.facebook.com/apps/',
        urlLabel: 'Abrir el portal de desarrolladores de Meta',
      },
      {
        label: 'En el panel de la aplicación busque «WhatsApp» y pulse «Set up». Siga los pasos para agregar un número de prueba. Vaya a «API Setup» y copie el token de acceso temporal',
      },
      {
        label: 'Copie su «Phone Number ID» (aparece en «API Setup») y el token de acceso. Péguelos abajo separados por dos puntos, por ejemplo 123456789:EAABx...',
      },
    ],
    inputFields: [
      { name: 'token', placeholder: 'Phone Number ID:token de acceso', type: 'password' },
    ],
  },
];
