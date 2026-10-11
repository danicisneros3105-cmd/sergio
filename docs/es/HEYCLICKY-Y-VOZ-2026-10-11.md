# Sergio: voz, pantalla y funciones inspiradas en HeyClicky

Revisión sobre `main` en `0549820a4137d8855db755c73ffc8dfd6ccb3f5b`.
Se conservan los Nodes nuevos, Josefin Sans, Workspace y el motor Swarm de su equipo.

## Cambios comprobados

- `server` y `desktop` instalan `google-genai>=2.29,<3`; lock actualizado.
  El instalador de escritorio sincroniza ambos extras. El actualizador comprueba
  `from google import genai` antes de instalar la app de Windows.
- `/v1/live/status` distingue SDK ausente y clave ausente. Tener SDK y clave
  configurados no demuestra que Google conceda cuota o acceso al modelo.
- La llamada mantiene audio bidireccional, transcripciones, interrupciones,
  reanudación y compresión de contexto. Su apertura tiene un límite de 18 segundos.
  El envío nativo sale del hilo del micrófono: FIFO de ocho paquetes de 100 ms.
  Ante congestión se reconecta; no acumula minutos de voz atrasada.
  La reproducción también tiene un tope de 12 segundos.
- En web, AudioWorklet sustituye ScriptProcessor. El micrófono silenciado no
  conserva audio para enviarlo al reactivarse. Se eliminó el estado «Pensando»
  provocado únicamente por una transcripción; las herramientas conservan su estado.
- No se cambia automáticamente a voz por turnos. Ese modo sigue disponible si
  se elige expresamente; `allow_turn_fallback` permite habilitar el respaldo.
- En escritorio, `live_screen` comparte capturas mientras la llamada está activa.
  El notch muestra «Pantalla en vivo». Se pausa desde el menú de la bandeja o con
  la herramienta de compartir pantalla. Con cámara abierta, ambos medios alternan.
  Web tiene un botón que usa el selector de pantalla del navegador.
  Se envía como máximo una imagen por segundo, limitada en tamaño; no se escriben
  esas capturas en disco. El proveedor recibe las imágenes: no es visión local.
- La política de atención usa el nombre, una ventana de seguimiento de 90 segundos,
  cambios de hablante y expresiones como «no te hablo». Suprime voz y acciones de
  conversaciones descartadas. Es una heurística: no identifica con certeza al
  destinatario, ni sustituye autenticación; una transcripción tardía puede llegar
  después de que empiece una respuesta. La proactividad del modelo ayuda cuando
  Google la admite. Voz/cámara no prueban identidad ni intención.
- Notch: resortes analíticos independientes de la frecuencia de cuadros, 60 Hz
  durante las transiciones y 20 Hz al quedar quieto; opción «Reducir movimiento».
  Se conserva el diseño original y el efecto de pliegue/blur existente.
- Cowork: entrada centrada, compositor más amplio, Ctrl/Command+Enter, errores
  visibles al cargar/decidir/detener y protección contra snapshots de otra tarea.
  Es una interfaz propia inspirada en chats de trabajo; no una copia certificada
  de ChatGPT ni una integración con sus servicios internos.
- Rutinas de Nodes: pausa/reanudación en la interfaz y API. Tres fallos reales
  pausan la rutina; errores de transporte de una vigilancia no consumen ese límite.

## Comparación con funciones públicas de HeyClicky

Fuentes oficiales: [producto](https://www.heyclicky.com/) y
[changelog 1.0.53](https://www.heyclicky.com/changelog).
Son referencias funcionales; no se incorporó código privado de HeyClicky.

| Función pública | Implementación y situación en Sergio |
|---|---|
| Conversación por voz y dictado | Gemini Live, dictado y atajos nativos; corregidos SDK y modo de respaldo |
| Ver la pantalla, enseñar y señalar/dibujar | Capturas Live y herramientas existentes de lectura, apuntado y control; requiere proveedor visual |
| Agentes y seguimiento | Nodes con hilos, memoria, archivos y actividad; Swarm y Cowork mantienen sus motores propios |
| Rutinas y vigilancias | Planificación y comparación de páginas/apps; añadida pausa por fallos y reanudación |
| Conectores y varias cuentas | MCP/CLI y APIs con nombres y secretos separados ya existen en Nodes. OAuth multicuenta completo de cada app no está implementado aquí |
| Notch/Home y archivos de agentes | Notch nativo, Nodes y Workspace existentes; mejoradas transiciones y compositor Cowork |
| Sugerencias proactivas, silencio en llamadas/DND y facturación | Sin paridad certificada con su servicio. No se añadieron conectores ficticios, cuotas comerciales ni anuncios de conexión sin comprobar |

No se afirma que estén todas las funciones de HeyClicky, ni que los frameworks
externos estén instalados íntegramente. Sus cuentas, servicios y mecanismos de
facturación no se obtienen copiando una interfaz. Los adaptadores existentes no
equivalen a instalar todos los repositorios en su «máxima potencia».

## Matemáticas y visión espacial verificables

`verified_math` usa AST limitado y fracciones exactas, sin eval, red ni modelo.
Acepta aritmética y ecuaciones lineales/cuadráticas con raíces racionales; devuelve
residuos al sustituir las soluciones. Limita longitud, nodos, potencias y tamaño
numérico. Los decimales conservan el literal escrito. Problemas no soportados y
raíces irracionales se reportan sin afirmar una verificación exacta.

Ejemplos ejecutados por las pruebas:

| Entrada | Resultado comprobado |
|---|---|
| `0.1+0.2` | `3/10`, decimal `0.3` |
| `2*x+3=11` | `x=4`, residuo `0` |
| `x**2-5*x+6=0` | `x=2` y `x=3`, residuos `0` |
| `x*x=2` | Raíces irracionales; no se marca como racional exacto verificado |

`scene_reason` recibe hasta 50 cajas con centros y dimensiones en m/cm/px.
Calcula distancias, solapamientos y una vista superior SVG con texto escapado.
Una propuesta se etiqueta como imaginada. Las medidas aportadas no prueban
la exactitud de su fuente. No calcula profundidad métrica de una foto sin
calibración ni convierte un modelo configurado en GPT-6 Astra.

Ambas herramientas están registradas, disponibles en Live aun sin agente
principal, y habilitables bajo las reglas de código de Nodes y la lista Swarm.

## Validación y límites

- 630 pruebas de escritorio aprobadas, 10 omitidas; arranque Windows real excluido.
- 210 pruebas de voz/backend/Nodes/Swarm/Cowork/Workspace aprobadas, 1 omitida.
- 148 pruebas web aprobadas; TypeScript y build Vite/PWA aprobados.
- Regresiones finales adicionales de búfer, precisión decimal y movimiento probadas.
- 1.798 archivos Python de código y pruebas parseados; Ruff de módulos y pruebas
  modificados aprobado; `uv lock --check` y sintaxis del actualizador Bash aprobados.
- Notch renderizado con Qt offscreen y pantalla activa. No es una medición de
  rendimiento en la GPU, el micrófono o los altavoces del usuario.
- Una batería amplia fue detenida por revisión automática al intentar llegar a
  `api.sendblue.co`. Se sustituyó el envío real en los tests webhook por dobles,
  y se bloquearon transportes HTTP externos en tests unitarios por defecto.
  Las pruebas aisladas de webhook/gestor aprobaron con simulaciones. El conector
  con cuenta real y la batería amplia interrumpida no se dan por certificados.
- No se ejecutaron conversaciones con cuentas Gemini reales, ni tareas sobre
  el Windows del usuario, ni se midió latencia real de extremo a extremo.
  No se promete latencia cero, identificación perfecta o ausencia de alucinaciones.

## Actualización

La rama de actualización incorpora `main` y el historial anterior mediante un
commit con ambos padres. Esto permite avanzar desde cualquiera de esos dos
historiales sin descartar commits. El actualizador conserva los datos y crea
una referencia de respaldo; se detiene ante cambios locales o divergencias reales.

La función PowerShell `Actualizar-Sergio` ya instalada debe seguir descargando
`codex/professional-reliability-audit`, sin fijar un hash antiguo. Los scripts
`scripts/actualizar-sergio.ps1` y `scripts/actualizar-sergio.sh` vuelven a estar en
esta versión. El script Bash instala voz y servidor y reconstruye la interfaz
antes de invocar el instalador Windows. La autenticación GitHub y la clave Gemini
configurada en su servidor siguen siendo necesarias.
