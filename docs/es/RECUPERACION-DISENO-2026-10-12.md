# Recuperación del trabajo de diseño — 2026-10-12

**Esta rama contiene una nota de recuperación, no una nueva versión funcional.**
El código de la actualización sigue local y no se ha publicado en main.

## Estado comprobado
- Main continúa en e1396e7374838c340b352d6134ebc5ab384ddf68.
- Trabajo local: /workspace/scratch/ea610e357c88/sergio-live.
- Se integró en esa copia el main reciente de Claude, conservando Nodes, voz Live,
  worklet, estilos y el flujo de reconocimiento facial del equipo.
- Se implementaron localmente Windows Hello para aprobar acciones, cifrado
  atómico de la galería y migración de galerías antiguas, rechazo de muestras
  incompletas y una hoja de consentimiento con acciones completas en texto plano.
- Anatomy está adaptada como skill interna, sin sección visible, con el kit MIT
  de wheresryan22/anatomy en el commit 240a9bf7c50cc6226148762a1017466fcbc08523.
- Se prepararon Estudio (32 herramientas), instalador selectivo WinGet, aplicaciones
  de ArtCraft, FreeCAD/Blender/Bonsai/LibreCAD, Kdenlive, VSCodium, adaptador REST
  de OpenDesign y un adaptador opcional de Kronos con pesos locales.
- LidoJS no se redistribuyó: la licencia del repo revisado no estaba declarada.
- Se revisaron capturas del frontend real con datos de prueba, y se corrigieron
  polos degenerados e iluminación de superficies redondas de los hologramas.

## Pruebas completadas antes de la desconexión
- 719 pruebas de escritorio: aprobadas; 4 omitidas.
- 460 pruebas de backend y módulos relacionados: aprobadas; 2 omitidas.
- 161 pruebas web y compilación de producción: aprobadas.
- 32 pruebas puras del kit Anatomy: aprobadas.
- Ruff de src/ y tests/: análisis y formato correctos.
- Una última revisión del texto completo de acciones largas se corrigió, pero
  la repetición final de pruebas no pudo confirmarse tras la desconexión.
- No se probó Windows Hello con hardware real ni inferencia de pesos de Kronos.
  Tampoco se certificaron todas las funciones de las aplicaciones externas.

## Bloqueo y siguiente paso
Las herramientas de ejecución y lectura del entorno devolvieron:
`409 Conflict, environment_offline: Environment is not connected`.
GitHub seguía accesible; main se dejó intacto para no publicar código que no
pudiera recuperarse y verificarse.

Al reanudar:
1. Recuperar el entorno y la copia local; conservar sus cambios.
2. Leer AGENTS.md y docs/BITACORA.md y comprobar si main avanzó.
3. Repetir las pruebas del último ajuste y revisar la galería/migración.
4. Quitar el harness temporal frontend/qa de los archivos a publicar.
5. Publicar solo los cambios de esta tarea; conservar todos los archivos de main.
6. Actualizar la bitácora y proporcionar el comando universal después de
   verificar que la nueva versión está efectivamente en main.

Una webcam RGB no ofrece las garantías de TrueDepth/Secure Enclave de Face ID.
La aprobación propuesta delega en Windows Hello y no trata una fotografía ni
un reto de movimiento como autorización para actuar.
