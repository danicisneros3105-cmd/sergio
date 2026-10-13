# Verificación de repositorios y equivalencia de Sergio

Fecha UTC: 2026-10-13; fecha del señor: 2026-10-12. Código publicado de partida:
`7acb4b0d05e90ab059762b92989b167b962be1a0`. Dos revisiones en paralelo:
inventario Creator y comparación de arquitectura/contratos. No se usaron cuentas
personales ni se autorizaron compras, mensajes o operaciones externas.

## Resultado comprobado

**No están incorporados todos los repositorios completos y no existe equivalencia
completa con Face ID, Muse, Dots, ChatGPT Work o Kimi K3.** No es solo falta de
un certificado: hay diferencias concretas en la implementación. Todos los nombres
de Creator están representados; una referencia o botón de apertura no incorpora
un motor. El informe Creator detalla cada programa y sus flujos existentes.

Se consultaron en GitHub 30 referencias de repositorio: 29 resolvieron y
`The-Swarm-Corporation/swarms` devolvió 404. La URL original de la organización
sí existe y muestra 163 repositorios; no significa que se hayan incorporado los
163. Se verificaron aparte SkillScanner y GraphWorkflow-Paper. El motor Swarms
revisado es `kyegomez/swarms`.

## Equivalencia: criterios, evidencia y resultado

| Referencia | Criterio importante | Evidencia de Sergio | Resultado |
|---|---|---|---|
| Face ID | Profundidad/IR, protección biométrica de hardware y resistencia medida a suplantación | Webcam RGB para reconocimiento; galería Fernet con clave de archivo. Consentimiento del compañero mediante Windows Hello. No hay TrueDepth/Secure Enclave ni estudio de falsas aceptaciones de la webcam | **No equivalente**. Windows Hello real requiere prueba en Windows compatible; una animación no acredita biometría |
| Muse | VM dedicada y Sentinel separado por el sistema operativo, permisos y secretos fuera del modelo | NodeStore crea una carpeta y NodeWorker usa el agente/procesos del host. Reglas, tickets y límites existen; no hay un Sentinel separado ni VM dedicada por Node | **Parcial funcionalmente; no equivalente en aislamiento** |
| OpenAI Dots | Computadora cloud por agente, trabajo continuo, conectores y modelo de frontera | Memoria, hilos, rutinas, objetivos, archivos y herramientas existen. Funcionan mientras el servidor esté activo; carpeta local no es computadora cloud aislada. No están los miles de apps del ecosistema ni su modelo como parte del repo | **Parcial; no equivalente** |
| ChatGPT Work | Modelo, creación de artefactos, trabajo colaborativo y ecosistema integrado | Cowork propio planifica pasos, presupuesto, aprobación, auditoría y exportaciones disponibles. Usa el proveedor configurado; pasos de pantalla se derivan al compañero. No incorpora el producto/modelo/ecosistema completo ni acredita diseño idéntico | **Parcial; no equivalente** |
| Kimi K3 Agent Swarm | Gran paralelismo real, modelo/orquestación entrenada y entregables | Motor propio: 300 subtareas, máximo 64 trabajadores simultáneos, 8 por defecto, presupuesto de 4.000 llamadas de subagentes. Kimi publica hasta 300 simultáneos; Sergio no incorpora K3/PARL ni sus pesos | **No equivalente**. Planificación y supervisión parecidas no acreditan velocidad/calidad iguales |
| HeyClicky | Voz/pantalla/guía y delegación, experiencia completa | Voz Live, capturas consentidas, overlays y motores propios tienen código. No incorpora su implementación privada ni se midió conversación humana, precisión de escucha o latencia frente a su producto | **Parcial; sin paridad de experiencia medida** |

No se realizaron benchmarks comparativos autenticados con los productos ni una
comparación visual pixel a pixel. Los tests controlados de Sergio no miden la
inteligencia de otro modelo, precisión biométrica o disponibilidad 24/7 del PC.

## Qué hay de cada grupo de repositorios

| Repositorio / grupo | Incorporación real | Lo que falta para llamarlo completo |
|---|---|---|
| Anil-matcha/open-dots | Patrón propio de pausa por fallos de rutinas; sin backend upstream | Motor, servicios y todos sus flujos. Su LICENSE no está disponible en el árbol consultado; no se copió su implementación |
| openclaw/openclaw | Adaptador CLI con revisión, proceso acotado y entorno sin claves heredadas | Runtime instalado y Gateway/agentes configurados y probados. Sergio no audita cada acción interna delegada |
| kyegomez/swarms | Workflows propios y validación de dependencias | Framework completo y sus arquitecturas; no se importa el paquete `swarms` |
| The-Swarm-Corporation | Ideas de SkillScanner y GraphWorkflow-Paper implementadas localmente | No están todos los repos de la organización; su URL `/swarms` no resolvió |
| browser-use/browser-use | Adaptador MCP y sesiones persistentes acotadas | Navegador, entorno y operaciones reales de navegación/extracción con su proveedor |
| marcoazeem/duo-open | Adaptación Qt del ángulo/inclinación/blur, crédito y licencia MIT | No es el motor Android/shader completo ni una copia idéntica de Apple |
| Notch SVG aportado | Gaussian blur 12 y matriz gooey 25/-12 en LiquidNotch; texto/controles fuera del filtro | Medición de rendimiento y comparación visual en el equipo real |
| Anatomy | Skill interna, 93 archivos, 3 adaptaciones y 90 recursos idénticos al pin upstream | No es todo el repo: de 122 blobs upstream se omitieron recursos generados/medios/infraestructura. Política aplicada no garantiza por sí misma el resultado visual |
| Creator | Catálogo y apertura/instalación de programas; adaptadores opcionales OpenDesign/Kronos; flujo Blender/DXF existente | Véase CREATOR-VERIFICACION-2026-10-13.md: instalación, proyectos guardados/exportados, Bonsai activo, servicio/pesos y pruebas reales; LidoJS es referencia |

La familia ArtCraft completa **sí figura en el catálogo**, con sus 13 repos
verificados: ArtCraft, PhotoCraft, LightCraft, VectorCraft, FilmCraft, EffectCraft,
DesignCraft, PdfCraft, WordCraft, SoundCraft, DeckCraft, CADCraft y GridCraft.
Sus aplicaciones completas siguen siendo externas; no están embebidas ni
instaladas por aparecer en ese catálogo.

## Pruebas realizadas ahora

- **170 tests Python aprobados, 2 omitidos**: Swarm, Cowork, Nodes, programas,
  rostros, consentimiento y rutas relacionadas. Incluyen presupuestos,
  cancelación, tickets ligados a la acción, APIs solo Dev, revocación y memoria.
- **161 tests frontend aprobados**; TypeScript y build de producción correctos.
- Ruff de `src/` y `tests/`: 1.821 archivos formateados y análisis correcto.
- **Browser-use 0.13.11 real**, instalado en entorno aislado de auditoría:
  inicialización y descubrimiento de **16 herramientas MCP a través del adaptador
  de Sergio**, seguido de cierre. Sin navegación, login ni inferencia pagada.
- **OpenClaw 2026.9.9 real**, instalado aparte sin ejecutar scripts de instalación:
  el adaptador CLI de Sergio ejecutó `--version`, código 0, sin timeout ni recorte.
  No se inició un Gateway ni se delegó una tarea real.
- **SwarmEngine real con respuestas controladas**: se pidieron 300 trabajadores;
  creó y terminó 300 subtareas, limitando la concurrencia solicitada a 64. Prueba
  del control del motor, no de inteligencia ni velocidad frente a Kimi.
- **Anatomy por hashes Git**: 90 archivos copiados coinciden exactamente con
  `240a9bf7c50cc6226148762a1017466fcbc08523`; no se sustituyó por otro HEAD.
- Árbol publicado leído íntegro: 5.936 entradas, sin truncamiento. Los archivos
  cambiados en esta revisión se publican sobre ese árbol completo.

Los motores externos de auditoría no se añaden automáticamente al instalador
de Sergio ni prueban qué está instalado en Windows del señor.

## Límite probado de la comprobación contra alucinaciones

`swarm/report.verify_report` coteja enlaces/cifras/documentos con resultados de
subagentes. Se introdujo una afirmación sintética sobre un precio de 999 USD
con una URL `.test`, tanto en el resultado como en el informe: devolvió `ok=true`.
No hubo proveedor real detrás. Esto demuestra que **coincidencia textual no es
verificación de la verdad externa**. El código ayuda a detectar información
nueva no respaldada; no elimina las alucinaciones ni valida las fuentes por sí solo.

## Correcciones y comprobación reproducible

Se corrigen afirmaciones anteriores: carpeta ≠ VM, reglas ≠ Sentinel,
300 subtareas ≠ 300 simultáneos, almacenamiento local ≠ datos nunca enviados
al proveedor. La interfaz de Swarm ahora muestra el límite simultáneo de 64.
Se conservan los motores y los cambios del equipo, sin elevar concurrencia o
inventar garantías para que una tabla parezca equivalente.

Inventario estructurado: `VERIFICACION-REPOS-2026-10-13.json`. Para comprobar
archivos de evidencia y ejecutables visibles en este host, sin instalar o
ejecutar aplicaciones, desde Ubuntu dentro de Sergio:

```bash
python3 scripts/verificar-integraciones.py
python3 scripts/verificar-integraciones.py --json
```

El diagnóstico distingue detección, referencia y código. No acredita todas las
funciones; WSL no revela automáticamente el inventario Windows. Para acreditar
un flujo profesional falta ejecutar el programa real, crear/guardar/exportar
su artefacto y revisar el resultado, además de probar Hello en hardware compatible.

## Fuentes primarias consultadas

- [Face ID, Apple](https://support.apple.com/en-us/102381).
- [Windows Hello, Microsoft](https://learn.microsoft.com/en-us/windows/apps/develop/security/windows-hello).
- [Muse, Meta](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/).
- [Dots, OpenAI](https://openai.com/index/introducing-dots/).
- [ChatGPT Work, OpenAI](https://openai.com/chatgpt-work/).
- [Agent Swarm, Moonshot](https://www.kimi.com/help/agent/agent-swarm).
- [HeyClicky](https://www.heyclicky.com/).
- [Repos The-Swarm-Corporation](https://github.com/orgs/The-Swarm-Corporation/repositories).
- Fuentes, pins y licencias de los 30 repos: inventario JSON y matriz Creator.
