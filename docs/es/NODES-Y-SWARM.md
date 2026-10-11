# Nodes y Agent Swarm: qué tienen y de dónde viene cada idea

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
| Sigue trabajando al cerrar la app | Sí: hilos de trabajo y un reloj cada 30 s en el servidor | `nodes/worker.py` (`NodeWorker`, `tick`) |
| Su propia computadora y navegador | Sí: una carpeta propia como disco, y las herramientas de navegador | `nodes/store.py` (`computer`), herramientas `browser_*` |
| Su PC, apagado por defecto | Sí: la regla «Usar su PC» empieza en **Nunca** | `store.py` (`RULES`, `pc`) |
| Memoria propia a largo plazo | Sí, y **usted la puede leer y corregir** (en Dots no se puede) | pestaña Memoria, `<recordar>` |
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
| **Sentinel**: permisos de lectura y de escritura por servicio | Sí: «Sin acceso · Leer · Leer y escribir» por app | `Node.apps`, `add_routine` |
| Personaje propio con el que habla | Sí: personaje de fieltro de diseño propio (forma, color, accesorio, ojos), que habla al leer en voz alta | `NodeCritter.tsx` |
| Forma de hablar | Sí: cercano, formal, breve, detallado, divertido, caballero | `store.TONES` |
| Plantillas para empezar | Sí: 12 | `skills.TEMPLATES` |
| Integraciones de negocio (Shopify, Slack, Dropbox) | Por conectores o por MCP | Conexiones → MCP |
| Controlar apps del ordenador | Sí, en Windows, con la regla «Usar su PC» (empieza en Nunca) | regla `pc` |
| Rellenar formularios, preparar compras | Prepara el carrito o el formulario; **pagar lo hace usted** | plantilla Compras, regla `purchases` |
| Sus datos no van a publicidad | Todo se queda en su equipo | — |
| **No tenemos**: dirección de correo propia del agente | Un Node puede vigilar su correo y reaccionar a lo que le llegue | rutina «Cuando llegue algo a una app» |
| **No tenemos**: avatar en videollamada en tiempo real | El personaje se anima con la voz en el chat; la llamada en tiempo real es con Sergio (modo de voz) | `VoiceMode.tsx` |
| **No tenemos**: llamadas a empresas ni compras con pago | A propósito: un Node nunca llama ni paga solo | `RULES`, reglas del planificador |
| **No tenemos**: gafas inteligentes | — | — |

## Agent Swarm frente a Kimi Agent Swarm (K3)

| Función de Kimi K3 | En Sergio | Dónde |
|---|---|---|
| Hasta 300 subagentes | Sí: `MAX_SUBTASKS = 300` | `swarm/engine.py` |
| Más de 4.000 llamadas a herramientas por tarea | Sí: un tope **compartido** de 4.000, reservado por agente para no pasarse nunca | `RUN_BUDGET`, `_reserve` |
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
  código lo marca. En el Agent Swarm, cada enlace y cada cifra del informe se
  cotejan con lo que trajeron los subagentes.

## Fuentes

- Meta Muse: [Wikipedia](https://en.wikipedia.org/wiki/Muse_(AI_agent)),
  [TechCrunch (lanzamiento)](https://techcrunch.com/2026/09/08/meta-debuts-its-muse-ai-agent-will-consumers-trust-it/),
  [TechCrunch (Connect 2026)](https://techcrunch.com/2026/09/23/everything-new-coming-to-metas-ai-agent-muse/),
  [TechCrunch (pequeñas empresas)](https://techcrunch.com/2026/09/29/meta-is-expanding-its-ai-agent-muse-to-small-businesses/),
  [Meta](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/).
- OpenAI Dots: [Composio](https://composio.dev/content/a-guide-to-chatgpt-dots-how-openai-s-always-on-agents-work),
  [MindStudio](https://www.mindstudio.ai/blog/chatgpt-dots-explained),
  [DEV (permisos)](https://dev.to/sword_luan_6dfb4e81cf5f15/openai-dots-explained-from-the-docs-the-permission-model-of-an-always-on-agent-5eoj).
  Casi todo viene de terceros, no de la documentación de OpenAI.
- Kimi Agent Swarm: [Centro de ayuda de Kimi](https://www.kimi.com/en/help/agent/agent-swarm),
  [Blog de Kimi](https://www.kimi.ai/blog/agent-swarm),
  [Zentor (K3)](https://zentor.ai/blog/kimi-k3-agent-swarm).
