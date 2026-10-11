# Auditoría de Sergio para desarrolladores y profesionales

Fecha: 2026-10-10. Base revisada: `7a031c33ff49e2e68df45f1e351b5fd388e8fbe7`.
Rama: `codex/professional-reliability-audit`.

## Dictamen

La segunda revisión añade ejecución de proyecto en contenedor configurable,
permisos estrictos de escritorio por defecto, captura de salida acotada,
limpieza de procesos hijos, transacciones reales de importación y recuperación
exclusiva de archivos. Las pruebas locales pasan; todavía no es una certificación
ni una prueba exhaustiva del producto. No se afirma que Sergio supere a la
competencia: no se ha ejecutado un benchmark equivalente entre productos.

### Segunda revisión: cambios nuevos

| Área | Comportamiento comprobado |
| --- | --- |
| Comandos | Captura concurrente de stdout/stderr con buffer acotado; limpieza del grupo POSIX incluso si el padre termina antes. Windows añade un Job Object antes de reanudar el proceso suspendido, para incluir sus hijos; falta ejecutar esta API en Windows real. |
| Proyecto aislado | `SERGIO_EXECUTION_MODE=container` exige `SERGIO_PROJECT_ROOT`, limita la ejecución a ese proyecto y exige Docker/Podman. No permite fallback local, descargas de imágenes, red, capacidades adicionales ni sistema raíz escribible. Límites de 512 MiB, dos CPU y 128 procesos. El proyecto montado sí es escribible. |
| Rutas alternativas | En el perfil de proyecto, el dispatcher permite únicamente shell_exec, code_interpreter, calculator y think propios. Bloquea herramientas de host, plugins, archivos, escritorio y red; las herramientas de escritorio también bloquean mutaciones en su propia frontera. El REPL en proceso queda desactivado. |
| Consentimiento | Solo el booleano `True` autoriza; errores o respuestas que solo son truthy deniegan. REPL y code_interpreter declaran confirmación y capacidad de ejecución. El escritorio exige confirmación por acción y habilidad que pueda modificar datos o usar aplicaciones. |
| Importación | Límite HTTP de 65 MiB antes del parser multipart, dos lotes simultáneos y 30 s para recibir el cuerpo. Límite agregado de texto. PDF/DOCX se procesan en un proceso desechable con timeout de 30 s; CPU de 20 s y memoria de 768 MiB en POSIX. Windows configura el límite de memoria en el Job, pendiente de prueba nativa. |
| SQLite | Un lote usa una sola transacción. Fallos revierten todos los chunks y FTS; los eventos de procedencia se publican después de confirmar. |
| Organización | Plan persistido una vez antes de mover: se evita la reescritura cuadrática del diario. Destinos reservados mediante hardlink exclusivo, sin sobrescritura incluso ante una colisión concurrente; deshacer recupera una interrupción entre link/unlink. Se excluyen archivos symlink y se rechazan destinos symlink. Si el filesystem no admite hardlinks, falla conservando el registro; no usa un fallback que sobrescriba. |
| Persistencia | fsync del archivo temporal antes de reemplazar perfil evolutivo y registro de movimientos. No constituye una garantía de durabilidad del filesystem ante corte eléctrico. |
| Interfaz | Páginas cargadas bajo demanda, indicador accesible de carga y límite de errores. El bundle de entrada baja de aproximadamente 1,13 MB a 407,72 kB. Otros módulos se cargan aparte; no equivale a reducir el total instalado ni a medir el arranque percibido. |
| Actualización | Scripts Bash y PowerShell validan el origen privado, rechazan cambios locales y divergencias, conservan referencias de respaldo y permiten fijar un SHA. Instalan dependencias bloqueadas del servidor, recompilan la interfaz y actualizan el escritorio. Un error detiene los pasos restantes; la referencia restaura código, no revierte dependencias ni el estado del instalador Windows. |

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

La suite final de la segunda revisión se documenta abajo; los datos de Globe
corresponden a la primera revisión, cuyo código no cambió en esta segunda etapa.

Las ejecuciones iniciales interrumpidas no se contabilizan como éxitos. Las
correcciones se verificaron primero por área y después con las suites generales.

| Comprobación | Resultado |
| --- | --- |
| Regresiones originales de las correcciones | 49 aprobadas |
| Importación, webhook simulado y visión/voz | 52 aprobadas, 3 omitidas |
| Flujo profesional, configuración e importación | 14 aprobadas |
| Shell: comandos reales, errores, timeout, entorno y UTF-8 | 21 aprobadas |
| Interfaz principal: Vitest | 115 aprobadas, 24 archivos |
| Interfaz principal: TypeScript y producción | Compila; aviso de bundle principal de aproximadamente 1,13 MB sin comprimir |
| Globe: producción | Compila; avisos de paquetes grandes |
| Python: suite general aislada | 11.144 aprobadas, 81 omitidas, sin fallos; un aviso de deprecación de asyncio en una prueba preexistente |
| Globe: pruebas de Node aisladas | 5.372 aprobadas y 1 omitida, más 14 pruebas de asignaciones de memoria aprobadas en Node 24 |
| Globe: límites de módulos | 834 módulos comprobados y comprobación de paquetes aprobada |
| Bloqueo de red Node | 2 pruebas aprobadas: rechazo externo y HTTP loopback real |
| Ruff del núcleo y pruebas | Sin errores |
| Formato del núcleo y pruebas | 1.744 archivos conformes tras corregir seis archivos de formato |
| Ruff incluyendo Windows | 187 avisos E501 y 10 I001 preexistentes; sin errores F |
| Bandit, Python y Windows (primera revisión) | 1.249 avisos: 1.143 bajos y 106 medios, ninguno alto. Se revisaron rutas sensibles de ejecución y carga de modelos; no se clasificó individualmente cada aviso. No equivale a ausencia de vulnerabilidades. |

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

## Riesgos y comprobaciones todavía pendientes

1. **Validación nativa Windows y de contenedores.** No hay Windows ni un daemon
   Docker/Podman aquí. Se verifican permisos con el servidor local y se prueba la
   construcción/limpieza del contenedor con dobles. Eso no demuestra resistencia
   a escapes de contenedor. Job Objects, DPAPI real, hardware, Blender, instalación,
   actualización y desinstalación requieren una máquina Windows de prueba.
2. **Alcance del perfil.** El modo normal sigue ejecutando código aprobado con los
   permisos de la cuenta. El contenedor es opt-in y requiere una imagen preparada.
   El perfil de proyecto restringe herramientas despachadas; no convierte todo el
   servidor, los SDK externos ni código de extensiones invocado directamente en
   un sandbox global. No usar el REPL local con entradas no confiables.
3. **CI de GitHub.** Los jobs observados terminan sin runner ni pasos. La conexión
   no expone la causa administrativa ni facturación; falta resolver la capacidad
   de ejecutar Actions y obtener una ejecución verde antes de integrar en main.
4. **Dependencias y bindings directos.** npm audit sigue bloqueado por el envío
   de metadatos privados a npm, sin aprobación específica para ese envío. El API
   Rust directo mantiene diferencias de timeout/entorno; las herramientas Python
   corregidas no lo usan para ejecutar comandos. Falta compilarlo y validarlo.
5. **Experiencia real.** Falta una jornada completa con personas, pruebas de
   accesibilidad en navegador, precisión de modelos, llamadas/cámara y métricas
   de latencia/memoria con hardware real. Persisten avisos de estilo de Windows
   y módulos grandes. Una confirmación por acción aumenta seguridad, pero puede
   interrumpir flujos largos; no se sustituyó por una sesión amplia sin medirla.

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

## Pruebas de uso cotidiano y medición reproducible

Se repite un flujo de desarrollador con 20 comandos autorizados, directorio de
trabajo fijo, errores de compilación conservados y ausencia de una credencial
sintética del entorno. Se prueban 100 informes organizados y devueltos byte por
byte, conflictos concurrentes y recuperación de un movimiento interrumpido.
También se prueba un fallo SQLite real después del primer documento, sin datos
parciales ni eventos falsos, y el rechazo por cuerpo y concurrencia antes del
parser. Las pruebas de actualización utilizan Git local y dobles de instaladores:
no instalaron ni iniciaron Sergio en un Windows real.

`PYTHONPATH=src:windows python scripts/benchmark-professional.py --iterations 20`
produce mediciones sintéticas locales sin servicios externos. En Linux/Python
3.12.14, con otras pruebas ejecutándose, 20 ciclos terminaron sin fallos:

| Flujo | Mediana | P95 |
| --- | ---: | ---: |
| Comando Python local | 65,07 ms | 468,23 ms |
| Organizar y deshacer 100 archivos | 23,35 ms | 44,13 ms |
| Guardar y buscar 100 registros SQLite | 8,04 ms | 50,10 ms |

Estas cifras no incluyen inferencia, interacción visual ni productos rivales.
No predicen el rendimiento en el PC del usuario. El reporte separa mejoras
comprobadas de comprobaciones que requieren otro entorno o autorización.

### Configurar el perfil de proyecto

El propietario configura el perfil en el entorno del proceso de Sergio, no
mediante argumentos que el modelo pueda escoger:

```bash
export SERGIO_EXECUTION_MODE=container
export SERGIO_PROJECT_ROOT="$HOME/proyectos/mi-app"
export SERGIO_SANDBOX_IMAGE="python:3.12-slim"
```

Debe existir el proyecto y estar disponible la imagen local en Docker o Podman.
El ejecutor usa `--pull=never`: no instala imágenes durante una acción. Para
proyectos que necesitan Git, Node o librerías específicas, preparar una imagen
de desarrollo y preferir su digest fijo. El proyecto montado es escribible y
sus archivos, incluidos secretos que estén dentro de él, quedan accesibles al
código aprobado. Elegir una carpeta de proyecto, nunca HOME ni la raíz del disco.
El modo se aplica al nuevo proceso de Sergio; reiniciar el servicio después de
configurar su entorno. La app de escritorio normal usa su propia confirmación
estricta; el modo de proyecto deshabilita mutaciones del escritorio desde el
servidor. No cambiarlo a local para eludir una acción rechazada.

### Actualizar una instalación existente

En Ubuntu/WSL, dentro del checkout privado de Sergio:

```bash
bash scripts/actualizar-sergio.sh codex/professional-reliability-audit SHA_VALIDADO
```

`SHA_VALIDADO` es el SHA completo del commit probado. El segundo argumento es
opcional y, si se omite, se usa la punta actual de la rama. Desde un checkout
Windows, `scripts/actualizar-sergio.ps1` acepta distribución, ruta del checkout
WSL, rama y commit. Se requiere autenticación Git al repo privado, uv, Node
22.22+ y npm 11.19+ menor que 12. El instalador de escritorio existente puede
descargar extras de voz/visión y reinicia la app; no se probó nativamente aquí.
La actualización no integra el PR en main.

### Resultado de la validación final

La suite limpia de Python terminó con **11.144 aprobadas, 81 omitidas, cero
fallos y cero errores**, más un aviso de deprecación preexistente. Después se
añadió una regresión de UTF-8 para Windows y se repitieron las pruebas de shell,
flujo profesional y archivos afectadas. Frontend mantiene 115 pruebas aprobadas
y build correcto. No se repitió Globe porque no se modificó en esta segunda
revisión; sus resultados anteriores se indican como tales.

El análisis Bandit de los módulos nuevos/centrales produce cuatro avisos bajos
y uno medio. Se revisaron: imports y llamadas explícitas de subprocess y la
ruta /tmp, que en ese caso es un tmpfs privado del contenedor. El uso deliberado
de shell en la API de comandos autorizados lleva una excepción documentada
B602, como el ejecutor anterior; no se presenta un análisis estático sin avisos
como prueba de aislamiento. Se retiró el archivo inválido residual de una
prueba anterior y la prueba de errores de colección usa ahora una carpeta
temporal fuera del checkout, para evitar contaminar ejecuciones posteriores.
