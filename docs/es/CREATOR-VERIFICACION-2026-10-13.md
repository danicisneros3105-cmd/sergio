# Creator / Estudio: verificación de presencia y alcance

Fecha: 2026-10-13. Referencia publicada comunicada para esta revisión: `7acb4b0d05e90ab059762b92989b167b962be1a0`. Lectura del árbol compartido durante la auditoría: HEAD `6fdab05b32aefb2db0bd41b3cc202d565377f713`. Auditoría de código y contratos; no instalación de los motores ni prueba física del PC del señor.

**Conclusión:** todos los nombres solicitados están representados, incluida la familia ArtCraft completa de 13 entradas. **No se puede confirmar que todos los repositorios estén incluidos íntegros y operativos dentro de Sergio.** Estudio es una mesa de acceso a aplicaciones externas: muchas entradas son catálogo, fuentes, instalación selectiva y apertura. LidoJS es solo referencia. OpenDesign y Kronos tienen adaptadores concretos y preparación opcional de repositorios completos aparte. Anatomy sí tiene recursos internos adaptados, con omisiones declaradas.

## Matriz exacta

En la columna «Presencia» se distingue código interno de acceso a una aplicación externa. «Abrir» no demuestra que un proyecto se haya creado, guardado o exportado.

| Solicitud y fuente | Presencia y conexión comprobadas en código | Requisito / límite pendiente |
|---|---|---|
| [FreeCAD](https://github.com/FreeCAD/FreeCAD) | Catálogo, paquete `FreeCAD.FreeCAD`, apertura Windows por alias `freecad`. | Instalar la aplicación. No hay copia íntegra del repo ni adaptador paramétrico FreeCAD específico comprobado. El flujo DXF existente es independiente. |
| [Blender](https://github.com/blender/blender) | Catálogo, `BlenderFoundation.Blender`, apertura. Además conserva flujo específico de generación de script `bpy`, kit, revisión de render, edición y archivo `.blend` en el compañero Windows. | Blender externo instalado y disponible; Gemini configurado para generar/revisar. No se incluye el motor Blender completo ni se ejecutó un render real en este host. |
| [Bonsai / BlenderBIM / IfcOpenShell](https://github.com/IfcOpenShell/IfcOpenShell) | Entrada `adapter=addon`, nota de instalación explícita; alias Windows `bonsai`/`blenderbim` apuntan a Blender. La ruta de apertura del catálogo rechaza el add-on. | Instalar y activar Bonsai aparte. Abrir Blender no prueba Bonsai; no hay comprobación de activación ni flujo IFC específico demostrado. |
| [LibreCAD](https://github.com/LibreCAD/LibreCAD) | Catálogo, `LibreCAD.LibreCAD`, apertura. Sergio ya genera DXF desde imagen o aristas de un modelo mediante OpenCV/ezdxf. | Instalar LibreCAD y abrir/revisar el DXF. Generar DXF no equivale a integrar todo LibreCAD ni probar su edición/exportación nativa. |
| ArtCraft y doce aplicaciones familiares (tabla siguiente) | Las 13 entradas tienen repo individual, Apache-2.0, releases y apertura por nombre mediante el compañero. | No tienen paquete WinGet revisado en este catálogo ni preparación de repo/runtime en el script. Instalar cada aplicación externa; verificar disponibilidad y funciones de su release. Modelos pueden requerir cuenta/API/créditos. |
| [Kdenlive](https://github.com/KDE/kdenlive) | Catálogo, `KDE.Kdenlive`, alias y apertura Windows. | Instalar Kdenlive. No se demostró creación/edición/exportación de proyecto Kdenlive mediante adaptador nativo. |
| [Kronos](https://github.com/shiyu-coder/Kronos) | `kronos_forecast`, validación OHLCV/fechas, worker CPU aislado y offline. Script clona repo externo fijado en `67b630e67f6a18c9e9be918d9b4337c960db1e9a` y prepara entorno. | Ejecutar preparación y aportar pesos locales compatibles de modelo/tokenizer. Sin inferencia real ni precisión calibrada comprobadas; no coloca órdenes. No es un motor ya incluido/instalado. |
| [LidoJS](https://github.com/lidojs/canva-clone) | `adapter=reference`, enlace y aviso de licencia pendiente. No tiene apertura, instalador ni adaptador funcional. | Repo revisado sin licencia declarada; dependencias/derechos pendientes. No redistribuido ni activado: esta solicitud no está funcionalmente satisfecha. |
| [OpenDesign](https://github.com/clawnify/OpenDesign) | Adaptador REST local: listar diseños/plantillas/marcas, obtener diseño/campos, crear, rellenar y actualizar. UI comprueba servicio, crea lienzo y abre editor externo. Script prepara repo completo fijado en `a0ea785a3be38f61a944571c7a7f72c2ce7d2c2f`, dependencias, tests/build y servicio local. | Ejecutar preparación/inicio aparte; API `8787`, editor `5178`. No se probó aquí el editor upstream funcionando. Exportación y fuentes pertenecen al editor; Sergio no tiene operación de exportación/publicación en su adaptador. |
| [VSCodium](https://github.com/VSCodium/vscodium) | Catálogo, `VSCodium.VSCodium`, alias `vscodium`/`codium`, apertura. | Instalar editor y extensiones deseadas. No incluye repo/runtime completo ni prueba de depuración/extensiones. |
| [Anatomy](https://github.com/wheresryan22/anatomy) | Skill interna MIT, `SOURCE.toml`, guía, kit, referencias, ejemplos y scripts. Política incluida en prompt base de agentes y Gemini Live; no es pestaña visible. | Adaptación fijada en `240a9bf7c50cc6226148762a1017466fcbc08523`; contenido generado, medios e infraestructura omitidos. Aplicar una política no prueba automáticamente la calidad de cada resultado. |

## ArtCraft: las 13 entradas, sin omitir aplicaciones

Todas constan en `src/openjarvis/professional/catalog.py` y tienen alias en `windows/sergio_escritorio/apps.py`. Se revisó su representación, no una sesión real en cada motor. El equipo principal verificó existencia de repositorios y licencia Apache-2.0 de toda la familia.

| Nombre | Repo fuente | Uso descrito en el catálogo |
|---|---|---|
| ArtCraft | [storytold/artcraft](https://github.com/storytold/artcraft) | Composición 2D/3D, imagen y vídeo |
| PhotoCraft | [storytold/photocraft](https://github.com/storytold/photocraft) | Imagen, capas, máscaras, PSD |
| LightCraft | [storytold/lightcraft](https://github.com/storytold/lightcraft) | Biblioteca fotográfica, RAW |
| VectorCraft | [storytold/vectorcraft](https://github.com/storytold/vectorcraft) | Vectores, tipografía |
| FilmCraft | [storytold/filmcraft](https://github.com/storytold/filmcraft) | Montaje de vídeo |
| EffectCraft | [storytold/effectcraft](https://github.com/storytold/effectcraft) | Motion graphics y efectos |
| DesignCraft | [storytold/designcraft](https://github.com/storytold/designcraft) | Maquetación y publicaciones |
| PdfCraft | [storytold/pdfcraft](https://github.com/storytold/pdfcraft) | Organizar y combinar PDF |
| WordCraft | [storytold/wordcraft](https://github.com/storytold/wordcraft) | Documentos de texto |
| SoundCraft | [storytold/soundcraft](https://github.com/storytold/soundcraft) | Audio, grabación y mezcla |
| DeckCraft | [storytold/deckcraft](https://github.com/storytold/deckcraft) | Presentaciones |
| CADCraft | [storytold/cadcraft](https://github.com/storytold/cadcraft) | CAD |
| GridCraft | [storytold/gridcraft](https://github.com/storytold/gridcraft) | Hojas de cálculo |

## Qué está conectado y dónde

- `frontend/src/App.tsx`: `/studio`, `/creator` y `/developer` muestran la misma `ProgramsPage`, no tres motores distintos. `frontend/src/pages/ProgramsPage.tsx` consume catálogo/apertura/instalador y controles OpenDesign.
- `src/openjarvis/professional/catalog.py`: 32 entradas totales; detección con `shutil.which`, alcance `server_path`. Los 32 programas del catálogo no son 32 instalaciones comprobadas.
- `src/openjarvis/professional/routes.py`: `/v1/programs`, instalador PowerShell selectivo y apertura mediante `DesktopActionTool`; router registrado en `src/openjarvis/server/app.py`.
- `src/openjarvis/tools/professional.py`: herramientas `professional_apps`, `opendesign`, `kronos_forecast`; registro importado por `src/openjarvis/tools/__init__.py`. Abrir una app entrega al compañero Windows una acción `open_app`; su índice consulta Inicio, accesos directos y App Paths en `windows/sergio_escritorio/apps.py`.
- `src/openjarvis/professional/opendesign.py`, `kronos.py`, `kronos_worker.py` y `scripts/preparar-integraciones.sh`: contratos y preparación opcional descritos arriba. Ese script solo prepara OpenDesign y Kronos.
- Blender/DXF existente: `src/openjarvis/tools/blender_pro.py`, `blender_model.py`, `blender_kit.py`, `cad.py`, `src/openjarvis/server/vision_blender_routes.py`; ejecución/revisión Windows en `windows/sergio_escritorio/app.py`, `media.py` y `windows_backend.py`. `blender_addons.py` atiende otros complementos; no demuestra activación Bonsai.
- Anatomy: `src/openjarvis/skills/bundled/anatomy/SOURCE.toml`, `SKILL.md`, `LICENSE`; `src/openjarvis/skills/design_policy.py`, `src/openjarvis/agents/_stubs.py` y `src/openjarvis/speech/gemini_live.py`. Comparación independiente del equipo principal: 93 archivos locales, 3 adaptaciones y 90 blobs idénticos de 122 blobs fuente upstream; no es copia íntegra.

## Ejemplos de uso diario y lo que necesitan

| Petición útil | Recorrido disponible | Condición para terminar de verdad |
|---|---|---|
| «Abra FreeCAD para revisar esta pieza» | Estudio o `professional_apps` → compañero → aplicación instalada. | FreeCAD y compañero funcionando; revisar el proyecto dentro de FreeCAD. Apertura sola no valida cotas ni fabrica una pieza. |
| «Modele esta lámpara y haga un plano» | Flujo Blender existente → script, `.blend`, render/revisión; aristas → DXF. | Blender, Gemini y dependencias DXF; ejecutar y revisar archivos reales. LibreCAD sirve para revisar/editar el DXF externo. |
| «Cambie los muros de este IFC» | Catálogo orienta a Bonsai sobre Blender. | Activar Bonsai y validar un flujo IFC real: ese trabajo completo no está demostrado por el catálogo. |
| «Prepare un cartel con mi plantilla» | OpenDesign: listar plantilla/campos → rellenar → revisar en editor. | Servicio local preparado e iniciado y plantilla real; exportar desde editor. LidoJS no sustituye este flujo. |
| «Edite este vídeo y mezcle el audio» | Abrir Kdenlive/FilmCraft y SoundCraft instalados. | Instalar los motores y comprobar proyecto, montaje, mezcla y exportación. Las entradas no automatizan ese flujo completo. |
| «Revele estas fotos, prepare PDF y diapositivas» | Abrir LightCraft/PhotoCraft, PdfCraft y DeckCraft. | Instalar cada aplicación y comprobar sus funciones reales; no basta un enlace al repo. |
| «Genere escenarios para estas velas históricas» | `kronos_forecast` valida datos y fechas → modelo local. | Repo/entorno/pesos preparados; comprobar inferencia. Resultado es escenario sin precisión calibrada, no recomendación ni orden. |
| «Abra el proyecto en VSCodium» | Alias/apertura del editor externo. | Editor instalado; revisar código y ejecutar pruebas/depuración del proyecto. |

## Evidencia y límites de esta revisión

El host Linux de auditoría detectó Git, uv, ripgrep y Node; no los programas creativos pedidos. Esto **no informa sobre lo instalado en Windows del señor**. La detección del PATH del servidor y el inventario Windows son mecanismos distintos; la ausencia en uno no demuestra ausencia en el otro.

Se leyó código de producción y tests. `tests/professional/test_integrations.py` usa detección sustituida y `httpx.MockTransport`: prueba contratos y rechazos, no un editor OpenDesign real. Las pruebas Blender sustituyen generación/modelos; sin ejecutable no acreditan render real. El flujo de informe en `tests/escritorio/test_professional_workflow.py` comprueba Python/archivos con entorno de pruebas, no las 13 aplicaciones ArtCraft. Los resultados generales de tests comunicados por el equipo principal no convierten estos límites en ejecución real de motores.

Pendiente para satisfacer «todos íntegros y funcionando»: instalación verificable de los motores externos, prueba de apertura en el PC real y un proyecto guardado/exportado por cada aplicación relevante; instalación/activación de Bonsai y prueba IFC; OpenDesign vivo y exportación revisada; Kronos con pesos e inferencia comprobada. LidoJS requiere aclarar licencia antes de incorporación. No hay evidencia para afirmar equivalencia con Muse, ChatGPT, Face ID ni motores completos ya instalados.
