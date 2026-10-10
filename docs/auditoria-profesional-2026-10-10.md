# Auditoría de Sergio para desarrolladores y profesionales

Fecha: 2026-10-10. Base revisada: `7a031c33ff49e2e68df45f1e351b5fd388e8fbe7`.
Rama: `codex/professional-reliability-audit`.

## Dictamen

Las correcciones mejoran consentimiento, privacidad, recuperación e importación
de documentos. La aplicación todavía necesita validación en Windows y aislamiento
de ejecución antes de usarla con datos profesionales sensibles. Esta revisión
combina lectura de rutas críticas, análisis estático, suites existentes y pruebas
de regresión. No constituye una certificación ni una prueba exhaustiva del producto.

## Problemas corregidos

| Problema observado | Cambio y comprobación |
| --- | --- |
| Ver una cara podía producir una aprobación sin consentimiento | Confirmación explícita local, seguida de comprobación de identidad. La herramienta exige que la respuesta corresponda exactamente a la petición. Pruebas de rechazo y de respuesta para otra acción. |
| El controlador ejecutaba Python, terminal y Blender sin una aprobación propia | Confirmación en el límite del controlador, con el contenido completo de la acción. Sin callback, con rechazo, error o pausa durante la espera, la acción no se ejecuta. Diálogo Qt con No por defecto y rechazo por timeout. |
| El perfil personal se guardaba como JSON plano | Utiliza el almacenamiento seguro existente: DPAPI en Windows y migración del JSON anterior al guardar. La prueba simula DPAPI; falta comprobar cifrado y recuperación con una cuenta real de Windows. En Linux se mantiene el formato marcado sin cifrado. |
| La memoria evolutiva podía quedar truncada o reconocer como aplicada una actualización fallida | Sustitución atómica de USER.md y del estado; el estado se actualiza después del perfil. Se prueba un fallo de reemplazo seguido de un reintento. |
| Dos organizaciones en el mismo segundo compartían el registro de deshacer | Registros únicos, serialización de operaciones y diario anterior a cada movimiento. Se prueba recuperación tras fallo parcial y conflictos de nombres sin sobrescribir trabajo nuevo. |
| Importación sin límite, análisis síncrono y escritura parcial antes de detectar un archivo inválido | Máximo 10 archivos, 20 MiB por archivo y 50 MiB por lote; texto extraído limitado a 5 Mi caracteres y título a 512. PDF/DOCX y SQLite pasan a un hilo; se valida todo el lote antes de escribir. Se cierra la conexión. DOCX limita el tamaño ZIP expandido. |
| Carga de pesos permitía deserialización genérica en versiones antiguas de PyTorch | `weights_only=True` explícito para el codificador de voz y el vocabulario visual. Cambio revisado estáticamente; falta ejecutarlo con los pesos reales. |
| Pruebas podían llegar a servicios reales | Respuestas Sendblue y sondeos de inicialización simulados. Bloqueo de conexiones Python fuera de loopback por defecto; preload equivalente para Node, probado con rechazo externo y servicio local real. |
| Detección de procesos daba falsos negativos con /proc del host y PID de un contenedor | Se comprueba el namespace de /proc; para procesos hijos se consulta waitid sin recolectarlos. El supervisor rechaza identidades registradas que ya no puede verificar. Regresiones de daemon y supervisor, incluidos procesos reales. |
| shell_exec cambiaba de garantías con Rust instalado y podía marcar un exit 42 como éxito | La herramienta Python utiliza siempre subprocess con entorno mínimo, timeout, código de salida real y truncado UTF-8 por bytes. Veinte pruebas incluyen procesos reales y simulan que Rust está disponible. El binding Rust directo todavía necesita equiparar ese contrato. |
| La suite tenía supuestos inválidos de entorno | La ausencia de pdfplumber se simula expresamente; el ID BM25 se valida como UUID v4, como lo generan tanto Rust como Python, sin exigir 32 caracteres. Se adapta la prueba de Blender para consentir la acción. |
| Globe podía ocupar todos los procesadores durante las pruebas | Su runner limita el paralelismo a cuatro procesos o a los disponibles, si son menos; conserva las pruebas de asignaciones en serie. |
| El cierre del vídeo CCTV podía lanzar un error al liberar su recurso | La liberación tolera fallos síncronos y asíncronos; una regresión comprueba que la limpieza y la notificación de fallo ocurren una sola vez. Se simula la red en las pruebas y se activa únicamente su cámara ficticia; CCTV real sigue desactivado por defecto. |

## Validación ejecutada

Las ejecuciones iniciales interrumpidas no se contabilizan como éxitos. Las
correcciones se verificaron primero por área y después con las suites generales.

| Comprobación | Resultado |
| --- | --- |
| Regresiones originales de las correcciones | 49 aprobadas |
| Importación, webhook simulado y visión/voz | 52 aprobadas, 3 omitidas |
| Flujo profesional, configuración e importación | 14 aprobadas |
| Shell: comandos reales, errores, timeout y entorno | 20 aprobadas |
| Interfaz principal: Vitest | 115 aprobadas, 24 archivos |
| Interfaz principal: TypeScript y producción | Compila; aviso de bundle principal de aproximadamente 1,13 MB sin comprimir |
| Globe: producción | Compila; avisos de paquetes grandes |
| Python: suite general aislada | 11.104 aprobadas, 80 omitidas, sin fallos; un aviso de deprecación de asyncio en una prueba preexistente |
| Globe: pruebas de Node aisladas | 5.372 aprobadas y 1 omitida, más 14 pruebas de asignaciones de memoria aprobadas en Node 24 |
| Globe: límites de módulos | 834 módulos comprobados y comprobación de paquetes aprobada |
| Bloqueo de red Node | 2 pruebas aprobadas: rechazo externo y HTTP loopback real |
| Ruff del núcleo y pruebas | Sin errores |
| Formato del núcleo y pruebas | 1.732 archivos conformes tras corregir seis archivos de formato |
| Ruff incluyendo Windows | 187 avisos E501 y 10 I001 preexistentes; sin errores F |
| Bandit, Python y Windows | 1.249 avisos: 1.143 bajos y 106 medios, ninguno alto. Se revisaron rutas sensibles de ejecución y carga de modelos; no se clasificó individualmente cada aviso. No equivale a ausencia de vulnerabilidades. |

Los números de las suites se solapan y **no deben sumarse**. El flujo profesional
genera un CSV mediante la herramienta Python, comprueba la petición aprobada,
previsualiza la organización sin efectos, aplica el movimiento y lo deshace,
comparando los bytes del resultado. La importación comprueba búsqueda en SQLite,
lotes inválidos sin escritura, límites, PDF malformado, DOCX expandido y un analizador
lento sin bloquear el event loop.

Se excluyen pruebas live, cloud, hub, live_external, modal, live_channel, docker,
nvidia, amd, apple y macos15. No se ha probado una jornada completa de una persona
ni la precisión de los modelos sobre tareas reales. No se realizaron pruebas live de llamadas, mensajes, compras, publicaciones
o modificaciones en cuentas de terceros.

## Riesgos pendientes, por prioridad

1. **Alta: aislamiento de código.** Un script aprobado conserva los permisos de
   la cuenta. REPL y evaluadores también usan exec/eval. La confirmación no es un
   sandbox. Crear un entorno por proyecto, restringir carpetas y red, y probar
   intentos de escape antes de procesar documentos no confiables.
2. **Alta: alcance de la automatización de escritorio.** Click, escritura y otras
   acciones pueden realizar operaciones sensibles por una ruta distinta a Python
   o terminal. Definir permisos de acciones, destinos y proyectos en todas las
   rutas del operador. El nuevo control no constituye una política global.
3. **Media: recursos y transacciones.** El límite de importación se aplica después
   del parser multipart; hace falta un límite HTTP de cuerpo y concurrencia en el
   servidor/proxy. Un PDF puede exigir recursos desproporcionados: el hilo mantiene
   disponible el event loop, pero no aísla memoria/CPU ni puede cancelar el parser.
   Un fallo de SQLite a mitad de un lote todavía puede dejar parte almacenada.
4. **Media: procesos y recuperación.** Verificar terminación de procesos hijos al
   expirar un comando; los timeouts actuales no garantizan detener todo el árbol.
   Las escrituras atómicas tampoco garantizan durabilidad ante corte de energía.
   Los registros PID antiguos o sin huella conservan compatibilidad; falta verificar
   identidad de procesos también en Windows. El ShellExecTool de Python ya aplica
   los límites, pero el binding Rust directo continúa sin timeout, entorno mínimo
   ni truncado y requiere un cambio compilado y probado por separado.
5. **Media: experiencia y publicación.** Reducir bundles con carga diferida y medir
   inicio frío, uso de memoria y latencia. Ejecutar QA de accesibilidad y teclado
   en un navegador real, y validar empaquetado, actualización y desinstalación en
   Windows. Corregir los avisos de estilo de Windows en un cambio separado.

## Competencia directa

Comparación documental, consultada el 2026-10-10. Las conclusiones sobre Sergio
son juicio técnico a partir del código y estas pruebas; no hay benchmark directo
de calidad, velocidad, precio o precisión entre productos.

| Producto | Referencia documentada | Aplicación para Sergio |
| --- | --- | --- |
| [Claude Code](https://code.claude.com/docs/en/permissions) | Permisos por herramienta, comando, ruta y dominio, modos y políticas compartidas; se aplican en el programa, independientemente de instrucciones al modelo | Pasar de confirmaciones generales a permisos verificables por proyecto y acción |
| [Cursor](https://cursor.com/docs/agent/security) | Lectura y cambios de workspace, aprobación de acciones sensibles y terminal; su documentación reconoce límites de las barreras basadas en revisión | Integrar revisión de diff, ejecución de tests y revertir cambios dentro del trabajo cotidiano del desarrollador |
| [OpenHands](https://docs.openhands.dev/openhands/usage/sandboxes/docker) | Docker es el entorno local recomendado; aporta aislamiento y reproducibilidad, y expone las carpetas montadas | Separar ejecución del agente del escritorio personal y montar únicamente el proyecto necesario |
| [Claude Cowork](https://claude.com/product/cowork) | Flujos para informes, hojas de cálculo, carpetas y conectores profesionales | Concentrar la experiencia en resultados revisables, procedencia y recuperación ante fallos |

El código de Sergio combina herramientas, modelos locales o externos, memoria,
interfaz web y automatización, voz y visión de Windows. Esa amplitud puede ser
útil para trabajo local. Para competir en equipos profesionales necesita demostrar
fiabilidad de extremo a extremo, permisos comprensibles y aislamiento, además de
la cantidad de funciones disponibles.

## Límites del entorno y comprobaciones bloqueadas

Entorno Linux, Python 3.12, Node 24.19 y npm 11.19 (versión exigida por frontend).
No se dispone de Windows, cámara/micrófono reales, GPU, Ruby, Cargo ni servicios
de inferencia configurados. La instalación del navegador de Playwright falló,
por lo que no se certifica QA visual interactiva. Las pruebas Qt son offscreen.

La revisión automática interrumpió ejecuciones que intentaban contactar Sendblue,
un Ollama privado y el registro npm. Se corrigieron mocks y se bloquearon conexiones
externas y descargas para continuar de forma aislada. `npm audit` permanece pendiente
porque enviaría el árbol de dependencias privado al registro. No se interpreta una
comprobación bloqueada como aprobada ni se afirma que se enviaran mensajes.

## Reproducción local

Instalar las dependencias de desarrollo del proyecto y `pytest-socket`, usar un
perfil de prueba y ejecutar Python con `PYTHONPATH=src:windows`,
`QT_QPA_PLATFORM=offscreen`, `NO_PROXY=127.0.0.1,localhost,::1`,
`pytest --allow-hosts=127.0.0.1,localhost,::1` y las exclusiones anteriores.
Para procesos hijos, usar proxies de prueba que rechacen conexiones, modo offline
de npm/uv/HuggingFace y `PIP_NO_INDEX=1`. El acceso externo requiere habilitación
explícita; no activar `--allow-external-network` para una suite de unidades.

Para Node, precargar `scripts/offline-node-tests.mjs` mediante `NODE_OPTIONS=--import`
con una ruta absoluta. Ejecutar `npm test` en frontend; en Globe, ejecutar su runner
de unidades y por separado sus comprobaciones de límites de módulos y build.
