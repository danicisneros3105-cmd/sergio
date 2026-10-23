# Lo que Sergio hace en el día a día

Revisión del 23 de octubre de 2026, sobre los 15 ejemplos del dueño. Objetivo:
**un asistente con control total del equipo**, que pide permiso antes de lo que
no tiene vuelta (enviar, publicar, llamar, comprar, borrar).

Estados:
- **Listo**: funciona hoy.
- **Parcial**: funciona con la pantalla o falta una pieza.
- **Falta**: no está hecho todavía.

## Cómo hace las cosas

1. **Primero con una herramienta propia.** Por ejemplo `photos_duplicates`,
   `pc_checkup`, `files_organize` o el organizador.
2. **Si no hay, con la pantalla, como una persona.** Ve la pantalla
   (`screen_read`) y usa el ratón y el teclado (`desktop_action` u
   `operate`) en Windows.
3. **Lo que no tiene vuelta, siempre con permiso.** Primero muestra una vista
   previa y pide el «sí» del dueño; después Windows confirma. Nada se borra
   para siempre: lo que se quita va a una carpeta para revisar, y siempre hay
   cómo deshacerlo.

## Los 15 ejemplos

| # | Pedido | Estado | Cómo / qué falta |
|---|---|---|---|
| 1 | Revisar WhatsApp y ponerme al día | Parcial | Abre WhatsApp en el PC, lee los chats en pantalla y los resume. WhatsApp no tiene una vía oficial para leer chats personales. La conexión no oficial (Baileys) puede hacer que bloqueen el número. Falta: un resumen guiado que recorra los chats sin leer. |
| 2 | Foto con Juan en historias de Instagram, con título y etiqueta | Parcial | Encontrar a Juan en la galería: Caras (con su consentimiento). Escribir el título: imita lo que el dueño publicó antes. La API de Instagram solo sube historias en cuentas de empresa o creador y no etiqueta personas en historias. Para eso Sergio usa Instagram en pantalla y **pide permiso antes de publicar**. Falta: buscar a una persona en toda la galería. |
| 3 | El PC está lento: ver qué lo frena y quitarlo | **Listo** | `pc_checkup`: memoria, procesador, disco, lo que más consume, lo que se abre al encender, temporales y papelera. Después, con permiso: borra los temporales, quita programas del inicio (se pueden volver a poner) y cierra programas. Nunca desinstala sin que el dueño diga cuál. |
| 4 | Ordenar la galería y borrar duplicadas | **Listo** | `photos_duplicates` encuentra la misma foto aunque esté achicada o guardada otra vez, y se queda con la de mejor calidad. Las sobrantes van a «Duplicados (Sergio)» y se pueden devolver. `files_organize` ordena por mes. |
| 5 | Modelo CAD 3D para la universidad | **Listo** | `blender_create`, FreeCAD y planos DXF (ezdxf), paso a paso con el dueño. |
| 6 | Leer lo que mandó Ana y reenviarlo a José como correo formal | Parcial | Lee el chat de Ana en pantalla y redacta el correo formal. La regla del dueño es **«correo: solo borradores»**: Sergio deja el borrador listo y el dueño lo envía. Si quiere que Sergio lo envíe tras su «sí», hay que cambiar esa regla, y la decide él. |
| 7 | Recordarme algo un día antes de una fecha | **Listo** | Organizador (recordatorios y alarmas) en Sergio Escritorio. |
| 8 | Alarma a las 6:40 con Daft Punk aunque el PC esté apagado | Parcial | Con el PC encendido o en suspensión: alarma del organizador. **Si el PC está apagado del todo, ningún programa del PC puede sonar.** Tiene que sonar el teléfono. Falta: que Sergio ponga la alarma en el teléfono del dueño, con un enlace o una app. |
| 9 | Ordenar los archivos del trabajo por carpetas | **Listo** | `files_organize`: primero la vista previa; se puede deshacer. |
| 10 | Cámara: ¿cómo me veo para la cita? | **Listo** | `camera_look` y Gemini Live con cámara. |
| 11 | Plataforma del colegio: recordatorios de tareas y exámenes | Falta | Google Classroom tiene API (con su inicio de sesión). Moodle tiene una clave personal. Las demás plataformas, por pantalla. Falta: el conector y que las fechas pasen al organizador. |
| 12 | Leer la plataforma, revisar tareas y hacerlas juntos | Parcial | Lee la plataforma en pantalla y trabaja la tarea con el dueño (coach de estudio). Necesita lo del punto 11 para avisar solo. |
| 13 | Presentación sobre la contaminación y enviarla | Parcial | Sergio hace la presentación con Diseño o como archivo de PowerPoint. Usar Canva necesita conectar su cuenta. El envío necesita el «sí» del dueño. |
| 14 | «Me siento mal» / Nodes que aconsejen sobre mi startup con mis archivos | **Listo** | Modo psicólogo, con líneas de crisis al instante y sin diagnosticar nunca. Para la startup: los Nodes (Rihno, Manchas, Hous, Tennessee) leen los archivos que el dueño les da. |
| 15 | Estudiar el estilo de un video de YouTube, hacer uno igual y subirlo al canal | Casi | `video_essay` estudia la referencia toma por toma y hace un ensayo editado a su nivel (guion, voz, cortes sobre las palabras, revisión y render). Busca clips libres en Pexels y Pixabay (con su clave gratuita); nunca toma videos ajenos. Falta: subir al canal con la API de YouTube, siempre después de que usted lo revise. |

## Lo que no depende del código

- **WhatsApp e Instagram personales** no tienen una vía oficial para leer y
  publicar como una persona. Por eso Sergio usa la pantalla y siempre pide
  permiso antes de enviar o publicar.
- **Con el PC apagado** solo puede sonar el teléfono.
- **Derechos de autor.** Solo se usan clips con licencia libre o del propio
  dueño.
- **Enviar correos.** Hoy Sergio solo deja borradores; cambiarlo lo decide el
  dueño.

## Orden propuesto para lo que falta

1. Resumen guiado de WhatsApp en pantalla (ejemplos 1 y 6).
2. Conector de Classroom y Moodle, con las fechas en el organizador (11 y 12).
3. Alarma en el teléfono (8).
4. Buscar a una persona en toda la galería (2).
5. Clips con licencia libre y subida a YouTube tras revisarlo (15).
