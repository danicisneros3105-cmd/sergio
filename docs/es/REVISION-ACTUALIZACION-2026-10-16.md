# Revisión de la actualización del 16 de octubre

Versión revisada: `6e6500b8dc4862f774d700091b0654b1a97002b0`, 32 commits después
de `79b7a0c`. Revisión y pruebas en una copia aislada; este informe no corrige
los fallos descritos ni certifica ejecución nativa de Windows.

## Hallazgos reproducidos, por prioridad

### 1. P1 — Una respuesta perdida puede duplicar una acción MCP

`src/openjarvis/mcp/hub.py`, líneas 576–588. `ConnectorHub.call` vuelve a llamar
a cualquier herramienta después de una excepción, incluida una de escritura.
Si el servicio creó un documento/factura pero se perdió su respuesta, la misma
autorización se utiliza para ejecutarlo otra vez.

Reproducción controlada: cliente que registra la escritura y después lanza un
timeout. Una llamada de Sergio produjo **dos ejecuciones**. No se modificaron
cuentas reales. Hay que evitar reintentar operaciones cuyo resultado sea
incierto, salvo garantía de idempotencia verificable; informar al usuario antes
de que decida repetirlas.

### 2. P1 — OAuth acepta enviar credenciales a un endpoint HTTP externo

`src/openjarvis/mcp/oauth.py`, líneas 313–329, y `hub.py`, línea 133.
La URL MCP inicial exige HTTPS salvo loopback, pero el endpoint de tokens
descubierto no aplica esa comprobación. `_token_request` envía código, verifier,
refresh token o secreto del cliente al endpoint indicado; el cliente sigue
redirecciones.

Reproducción con `httpx.MockTransport`: recurso HTTPS y endpoint de token HTTP
externo; se aceptó una petición HTTP cuyo formulario incluía un secreto de
prueba. No se transmitieron credenciales por red. Hay que validar endpoints de
OAuth y cada destino/redirección, conservar excepciones locales explícitas y
rechazar descensos a HTTP antes de enviar secretos.

### 3. P1 — El retorno OAuth falla cuando la API tiene autenticación

`src/openjarvis/server/auth_middleware.py`, `_requires_auth`, y
`src/openjarvis/server/mobile.py`, `_is_public`; ruta de retorno en
`server/mcp_routes.py:186`. El navegador del proveedor regresa sin el encabezado
Bearer de Sergio. El middleware protege todo `/v1/`, incluido el callback.

Reproducción con FastAPI, router MCP y `AuthMiddleware(api_key=...)`:
`GET /v1/mcp/oauth/callback?...` devolvió **401, Missing Authorization header**
antes de llegar al controlador. Las pruebas directas de Hub no detectan esta
interacción. Es necesario permitir exclusivamente el callback correspondiente
con validación de state, PKCE y caducidad, manteniendo protegidas las demás
rutas; revisar también la puerta del acceso remoto.

### 4. P1 — Quitar un marketplace acepta rutas fuera de su directorio

`src/openjarvis/plugins/claude_format.py`, líneas 174–179; entrada CLI en
`src/openjarvis/cli/plugin_cmd.py:483`. `remove_marketplace` no exige un nombre
válido ni que esté registrado, y hace `rmtree(markets_dir / name)`.

Reproducción solo dentro de un directorio temporal: un nombre con recorrido
de padres borró una carpeta ajena a marketplaces, aunque no había ningún
marketplace registrado con ese nombre. Requiere invocar la operación con ese
argumento; no se demuestra acceso remoto sin autenticar. Validar identificador,
existencia y confinamiento de la ruta antes de modificar estado o borrar.

### 5. P2 — La limpieza de Papelera cuenta desde la edición, no desde el borrado

`src/openjarvis/workspace/store.py`, líneas 383–407. Al mover una página a
Papelera se conserva su mtime. `empty_trash` usa ese mtime para sus 30 días.

Reproducción: una página sin editar durante 60 días, borrada ahora, fue eliminada
inmediatamente al ejecutar `empty_trash()`; resultado **1 archivo eliminado**.
Es un defecto del almacenamiento que ya existía, relevante para la nueva
Papelera; no afirmo que la interfaz invoque automáticamente esta limpieza.
Guardar fecha de eliminación o reiniciar la fecha del archivo al moverlo.

## Qué se verificó

- Árbol remoto: 6.126 entradas, sin truncamiento. Se materializaron 5.461 archivos
  idénticos por SHA de blob, normalizando únicamente el LF añadido por el canal
  de descarga. Siete binarios quedaron excluidos: tres favicons/iconos de
  aplicaciones, el instalador EXE, su icono y dos pesos YOLO. No se ejecutaron.
- Frontend: **219 pruebas aprobadas**, TypeScript y build de producción correctos.
  La compilación mantiene advertencias de chunks grandes e imports mixtos.
- Escritorio y voz: **816 pruebas aprobadas, 4 omitidas**, Qt fuera de pantalla.
  No equivale a probar micrófono, cámara, GPU, Hello o instalador en Windows.
- MCP, plugins, Workspace, Creator, Cowork, Nodes, Swarm y rutas/agentes:
  **389 aprobadas, 4 omitidas, 2 fallidas**. Los dos fallos ya constaban en la
  bitácora del equipo y exigen igualdad exacta del system prompt; en las dos
  reproducciones se conserva el prompt personalizado, con Anatomy añadida.
  No se ocultan ni se cuentan como aprobados.
- Ruff: análisis correcto y **1.872 archivos** con formato correcto.
- La primera ejecución necesitó lxml en el entorno de revisión; tras instalarlo,
  pasaron el recortador y los tests de límites de subida, incluido el PDF
  malformado. Se usaron npm 11.19.0 y Node 24.19.0 para instalar el lockfile.

## Mejoras reales encontradas

Hay implementación nueva de OAuth/PKCE y renovación de tokens, permisos por
herramienta, importación de plugins de marketplaces, flujo Cowork con plan y
continuaciones, Workspace local con Biblioteca/Papelera/Presentar, y Creator
con editores y conexión a programas externos. El iframe principal de Prototipos
permite scripts sin `allow-same-origin`, preservando esa frontera de origen.
La existencia de estos componentes supera el catálogo de la revisión anterior;
no demuestra que todos los servicios comerciales estén conectados.

## Pantalla y uso diario: límites de esta revisión

El objetivo de 32 FPS sigue configurado. El carril de vídeo conserva el último
frame y descarta anteriores si el envío se atrasa. `_video_sent` cuenta envíos
terminados por el SDK: no es una confirmación de cada imagen interpretada por
Gemini. No hice una llamada pagada ni repetí aquí la medición del otro agente.
No certifico 32 FPS efectivos estables, latencia de conversación ni ausencia de
alucinaciones. No se bajó la frecuencia ni se modificó el código de producción.

**Conclusión:** frontend compilable y pruebas amplias, pero quedan bloqueos de
autenticación, repetición de acciones y manejo de credenciales/rutas que deben
corregirse antes de dar esta versión por lista para uso diario con cuentas reales.
