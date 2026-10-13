# Nodes y Agent Swarm: qué tienen y de dónde viene cada idea

Esta comparación queda corregida por `VERIFICACION-REPOS-Y-PARIDAD-2026-10-13.md`.
Es una comparación de funciones; no acredita equivalencia completa.

Auditoría del código de octubre de 2026. Compara los **Nodes** de Sergio con
**Dots** (OpenAI) y **Muse** (Meta), y el **Agent Swarm** con el **Agent
Swarm de Kimi K3** (Moonshot). Cada fila dice dónde está en el código. Lo
que no tenemos también se dice, y por qué.

Los Nodes y el Agent Swarm son **dos cosas distintas**:

| | Nodes | Agent Swarm |
|---|---|---|
| Para qué | Un empleado digital que **sigue trabajando** días y semanas | **Una tarea enorme y puntual**, hecha a la vez por muchos agentes |
| Cuánto dura | Hasta que usted lo borre | Minutos; luego **se disuelve** |
| Código | `src/openjarvis/nodes/` | `src/openjarvis/swarm/` |
| Pantalla | `/nodes` | `/swarm` |

## Nodes frente a OpenAI Dots

| Función de Dots | En Sergio | Dónde |
|---|---|---|
| Sigue trabajando al cerrar la app | Solo mientras el servidor esté encendido: hilos y reloj cada 30 s | `nodes/worker.py` (`NodeWorker`, `tick`) |
| Su propia computadora y navegador | Parcial: carpeta y herramientas; no una VM ni un navegador aislado por Node | `nodes/store.py` (`computer`), herramientas `browser_*` |
| Su PC, apagado por defecto | Sí: la regla «Usar su PC» empieza en **Nunca** | `store.py` (`RULES`, `pc`) |
| Memoria propia a largo plazo | Sí: memoria local que usted puede leer y corregir; no se certifican diferencias con la memoria de Dots | pestaña Memoria, `<recordar>` |
| Qué hace solo / qué pregunta / qué le devuelve | Sí: Solo · Preguntar · Nunca por categoría, y «Tomar el control» | `RULES`, `request_approval`, `needs_you` |
| Leer es libre; cambiar algo o enviar pide permiso | Sí: enviar, borrar y pagar nunca son automáticos | `RULES` (`messages`, `delete`, `purchases`) |
| Revisión antes de actuar | Sí, **por código**: lista de comandos permitidos, rutas de API confinadas, nada de shell | `nodes/connections.py` |
| Rutinas y avisos | Sí: horario, cada X minutos, cambio en una web, algo nuevo en una app; le avisa por su canal | `skills.py`, `worker._tell_owner` |
| Apps conectadas (Slack, GitHub…) | Sí, las que usted conecte, y además MCP y CLI | pestañas Apps y Conexiones |
| Un Dot por cuenta | Sin límite de Nodes | — |

## Nodes frente a Meta Muse

| Función de Muse | En Sergio | Dónde |
|---|---|---|
| Trabaja en segundo plano y vuelve cuando algo cambia o necesita aprobación | Sí: los vigilantes son código; el modelo solo despierta con un cambio real | `skills.check_page`, `skills.app_items` |
| Conectar apps de una en una | Sí | pestaña Apps |
| **Sentinel** separado por el sistema operativo | No. Hay reglas «Sin acceso · Leer · Leer y escribir», no un Sentinel aislado | `Node.apps`, `add_routine` |
| Personaje propio con el que habla | Sí: personaje de fieltro de diseño propio (forma, color, accesorio, ojos), que habla al leer en voz alta | `NodeCritter.tsx` |
| Forma de hablar | Sí: cercano, formal, breve, detallado, divertido, caballero | `store.TONES` |
| Plantillas para empezar | Sí: 12 | `skills.TEMPLATES` |
| Integraciones de negocio (Shopify, Slack, Dropbox) | Por conectores o por MCP | Conexiones → MCP |
| Controlar apps del ordenador | Sí, en Windows, con la regla «Usar su PC» (empieza en Nunca) | regla `pc` |
| Rellenar formularios, preparar compras | Prepara el carrito o el formulario; **pagar lo hace usted** | plantilla Compras, regla `purchases` |
| Privacidad frente a proveedores | Almacenamiento local; los prompts, capturas o datos usados pueden enviarse al proveedor configurado | Configuración del proveedor y permisos |
| **No tenemos**: dirección de correo propia del agente | Un Node puede vigilar su correo y reaccionar a lo que le llegue | rutina «Cuando llegue algo a una app» |
| **No tenemos**: avatar en videollamada en tiempo real | El personaje se anima con la voz en el chat; la llamada en tiempo real es con Sergio (modo de voz) | `lib/liveSession.ts` |
| **No tenemos**: llamadas a empresas ni compras con pago | A propósito: un Node nunca llama ni paga solo | `RULES`, reglas del planificador |
| **No tenemos**: gafas inteligentes | — | — |

## Agent Swarm frente a Kimi Agent Swarm (K3)

| Función de Kimi K3 | En Sergio | Dónde |
|---|---|---|
| Hasta 300 subagentes simultáneos | Parcial: 300 subtareas, máximo 64 trabajadores a la vez (8 por defecto) | `swarm/engine.py` |
| Más de 4.000 llamadas a herramientas por tarea | No es el mismo límite: tope compartido de 4.000 llamadas de subagentes, no más de 4.000 | `RUN_BUDGET`, `_reserve` |
| Sin roles fijos: el orquestador inventa los especialistas | Sí | `PLAN_PROMPT`, `plan_subtasks` |
| Búsqueda en paralelo a gran escala | Sí: un **explorador** mira el terreno antes de repartir | `SCOUT_PROMPT`, `_scout` |
| Procesar lotes (cientos de documentos) | Sí: un lector por documento | `plan_subtasks` |
| Ver a los agentes trabajar | Sí: cuadrícula en vivo con la herramienta que usa cada uno | evento `tool`, `SwarmPage.tsx` |
| Resistente a fallos | Sí: reintentos con espera (2 s y 6 s) | `RETRY_DELAYS` |
| Un supervisor que une y revisa | Sí, y además **comprobación por código**: enlaces, cifras y documentos | `swarm/report.py` |
| Entregables | Markdown con fuentes, CSV de las tablas, JSON, página del Workspace | `/v1/swarm/{id}/export`, `/workspace` |
| ~4,5 veces más rápido que un solo agente | Depende del modelo y de cuántos van a la vez (4–64) | — |

## Contra las alucinaciones y el retraso: lo que hace el código

- **Vigilar** una web o una app lo hace el código (comparar el texto, sacar
  precios, mirar la base de datos de sus apps). El modelo solo se despierta
  si hay un cambio real.
- **Ejecutar** comandos, MCP y APIs lo hace el código con lo que usted
  permitió, y el resultado real vuelve al Node.
- **Comprobar**: si un Node dice que guardó un archivo que no existe, el
  código lo marca. En el Agent Swarm, enlaces y cifras del informe se
  cotejan con lo que trajeron los subagentes. Coincidir con su texto no verifica
  que la fuente externa sea verdadera ni elimina las alucinaciones.

## Fuentes primarias

- [Dots, OpenAI](https://openai.com/index/introducing-dots/).
- [Muse, Meta](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/).
- [Agent Swarm, Moonshot](https://www.kimi.com/help/agent/agent-swarm).
- [ChatGPT Work, OpenAI](https://openai.com/chatgpt-work/).
