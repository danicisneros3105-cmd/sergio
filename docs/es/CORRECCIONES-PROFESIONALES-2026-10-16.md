# Correcciones profesionales — 16 de octubre de 2026

Base: `9c93b13`. Checkpoint remoto: `b2f4723`. Cambios de interfaz y programas
del equipo conservados. No se clonan productos ni se certifica equivalencia
con software propietario mediante nombres, instaladores o tests unitarios.

## Tareas y resultado

| Tarea | Entregado | Verificación pendiente |
| --- | --- | --- |
| 1. Cinco fallos de la auditoría | Escrituras MCP sin reintento incierto; OAuth TLS y redirecciones controladas; callback público exacto con state de un uso/15 minutos y PKCE; marketplace confinado; Papelera conserva 30 días desde el borrado, también para archivos antiguos. | Ninguno de estos cinco casos reproducidos queda abierto. |
| 2. Conexión de apps | OAuth completo, renovación, credenciales editables, Bearer/API headers, secretos privados desde creación y migración de configuraciones antiguas. Retorno mediante ventana verificada o consulta del estado real al servidor. Permisos por herramienta conservados. | Iniciar sesión en cada cuenta y probar sus operaciones reales. Gmail necesita proyecto/Client ID; Figma remoto exige aprobación del cliente por Figma. |
| 3. Plugins | Marketplaces sin borrado fuera de carpeta; plugins homónimos separados en disco y al cargar herramientas; errores parciales visibles; cabeceras MCP preservadas; protección del destino SSE. | No se ejecutan hooks, por decisión del proyecto. No se garantiza compatibilidad con cada extensión privada. |
| 4. Vídeo | Objetivo local por defecto `32.310520139305` FPS, sin redondear a 32. Carril independiente, cadencia regulada, último cuadro disponible, envíos SDK y descartes medidos. La telemetría devuelve `provider_verified: false` y `provider_fps: null`. | Recepción e interpretación exactas en Gemini no certificadas. Su documentación Live indica máximo 1 FPS; un envío del SDK no acredita interpretación del modelo. |
| 5. Caché | Configuración reutilizada con invalidación por identidad/fecha/tamaño de archivo y copia defensiva; cliente HTTP reutilizado. Diagnóstico público con caché de una hora y `--refresh`. | El caché de tokens del proveedor depende del proveedor; no se promete un porcentaje de ahorro de inferencia. |

## Evidencia de pruebas

- **755 pruebas Python focalizadas pasan**, 8 omitidas; **816 de
  escritorio/voz pasan**, 4 omitidas. Total: **1.571 pasan**, 12 omitidas.
- **223 pruebas web en 49 archivos pasan**; TypeScript/build y Ruff correctos.
- Suites de skills, MCP, plugins, Workspace, Creator, Cowork, Nodes, Swarm,
  rutas y agentes ejecutadas; escritorio/voz completo con Qt offscreen.
- Flujos completos contra servidores reales del SDK oficial MCP: OAuth,
  PKCE, callback con ambas capas de autenticación activas, refresh, permisos,
  HTTP con API key y stdio. Datos y credenciales exclusivamente de prueba.
- Cuatro pruebas live requieren Ollama `qwen3.5:4b` y autorización explícita
  `OPENJARVIS_TEST_LIVE_NETWORK=1`. Ahora se omiten sin ese requisito;
  no se presentan como pruebas reales de inferencia superadas.
- Web: TypeScript/build y pruebas Vitest, incluidos mensajes de ventanas
  falsificados, popup bloqueado, expiración y confirmación desde servidor.
- Caché: 999 aciertos/1.000 consultas, 1 lectura JSON, 19,57 ms totales en
  este contenedor; no es una medición del PC de Windows.
- Prueba breve de cadencia con sesión sintética: objetivo 32.310520139305;
  15 cuadros enviados, promedio observado 32,235 FPS. Confirma variación
  temporal; no demuestra la tasa de recepción de Gemini.
- Chromium no pudo instalarse: la descarga devolvió un ZIP inválido. No se
  completó QA con navegador completo, Windows físico ni participantes humanos.

## Comprobación pública de conectores

Catálogo: **72 entradas**, **65 remotas** y 7 locales. Se consultaron las 65
remotas sin tokens, registro de clientes, ejecución de herramientas ni acceso
a cuentas. Resultado puntual: **42 con metadatos OAuth verificados**, 5 con
respuesta inicial solamente, 4 con fallback no verificado y 14 sin verificar.
**Cuentas autenticadas verificadas: 0**.

Gmail publicó el emisor `accounts.google.com`; Notion, `mcp.notion.com`;
Higgsfield, `clerk.higgsfield.ai`. Esto acredita descubrimiento, no permisos,
facturación ni operaciones de la cuenta. Los 18 casos que necesitan revisión
de acceso, metadatos o proveedor constan en
[la evidencia JSON](CONECTORES-COMPROBACION-2026-10-16.json).

Diagnóstico reproducible, desde el repositorio:

```bash
uv run python scripts/auditar-conectores.py
uv run python scripts/auditar-conectores.py --live
uv run python scripts/auditar-conectores.py --live --refresh
```

## Comparación con referencias profesionales

Comparación funcional, sin ranking universal de «más avanzado» y sin afirmar
igualdad del código propietario. Se conservan las integraciones existentes.

| Área | Referencia investigada | Sergio y diferencia que sigue abierta |
| --- | --- | --- |
| Conectores y plugins | [Claude Code MCP](https://code.claude.com/docs/en/mcp) y [marketplaces](https://code.claude.com/docs/en/plugin-marketplaces) | Se endurecieron autenticación, permisos e importación. No se acredita paridad total de recursos, prompts, elicitation, notificaciones o transportes de cada cliente. |
| Workspace | [Notion: relaciones/rollups](https://www.notion.com/help/relations-and-rollups) y [offline](https://www.notion.com/help/use-pages-offline) | Editor, bases, relaciones y sincronización existentes probados localmente. Colaboración y permisos equivalentes a escala empresarial no certificados. |
| Diseño | [Canva SDK/API](https://www.canva.dev/docs/apps/rest-apis/) y [Figma MCP](https://developers.figma.com/docs/figma-mcp-server/remote-server-installation/) | Editor interno y adaptadores existentes. Integrar un programa no expone automáticamente todas sus funciones; Figma requiere cliente autorizado o alternativa de escritorio. |
| Vídeo | [Premiere](https://helpx.adobe.com/premiere/desktop/collaborate-with-others/collaboration-in-premiere.html) y [Kdenlive](https://docs.kdenlive.org/en/) | Programas externos y herramientas existentes conservados. No se probó una producción completa, colaboración editorial ni todos los códecs. |
| Arquitectura/BIM | [Bonsai](https://docs.bonsaibim.org/), FreeCAD y LibreCAD | Instaladores y adaptadores existentes; no certificación integral de modelado, documentación y formatos en Windows real. |
| Desarrollo | [VS Code](https://code.visualstudio.com/docs), VSCodium y Claude Code | Lanzamiento/editor, CLI, MCP, herramientas y Cowork. No se ejecutaron todos los lenguajes, depuradores o extensiones. |
| Finanzas | [Kronos](https://github.com/shiyu-coder/Kronos) | Modelo de series financieras y adaptador existentes; no acredita un terminal de mercado completo ni exactitud predictiva. |
| Voz y visión | [Gemini Live](https://ai.google.dev/gemini-api/docs/live-api/capabilities) | Cadencia y métricas corregidas; latencia y recepción reales dependen de red, cuenta y proveedor. |
| Identidad | [Face ID](https://support.apple.com/en-us/102381) y [Windows Hello](https://support.microsoft.com/en-us/windows/security/configure-windows-hello) | Delegación a Windows Hello conservada. Una webcam y una animación no demuestran equivalencia con TrueDepth/Secure Enclave. |
| Nodes y Swarm | Implementaciones y pruebas del repositorio | Persistencia/orquestación probadas localmente. No se certifica igualdad con Muse/Kimi ni escala y calidad de modelos propietarios. |

## Aceptación en cuentas reales

Pendiente: conectar un Workspace de Notion y consultar una página conocida;
crear un borrador Gmail; generar una pieza Higgsfield con créditos del usuario;
verificar permisos y revocación en cada cuenta; realizar una sesión prolongada
de voz/pantalla en el PC de destino. Las operaciones con coste, contenido
privado o cambios externos requieren la cuenta y el consentimiento del usuario.

Estas condiciones no se sustituyen con respuestas simuladas ni indicadores
«Conectado» sin herramientas disponibles.
