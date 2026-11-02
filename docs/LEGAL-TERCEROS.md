# Lo de terceros que usa Sergio: qué se puede vender y qué no

Revisión del 2 de noviembre de 2026. **No es asesoría legal**: es un inventario
técnico para llevar a un abogado de propiedad intelectual y de tecnología
(idealmente de EE. UU. o del Reino Unido, porque la compañía es internacional).

## Lo primero: no hay «vacíos» en los que apoyar un negocio

El dueño pidió buscar vacíos legales. Esta revisión **no** busca formas de
saltarse licencias o términos de servicio, por tres razones prácticas:

1. Una app que se vende a miles de personas es el blanco ideal de un reclamo.
   Un vacío que sirve para uso personal no sirve para un producto: el que
   demanda ve el producto, no el truco.
2. «Uso justo» (*fair use*) y «uso nominativo» son defensas **que se prueban
   ante un juez, caso por caso**. No dan permiso por adelantado. Sirven para
   citar y nombrar, no para construir una función central sobre el material de
   otro.
3. Los términos de servicio (YouTube, Instagram…) se rompen sin necesidad de
   un juez: la cuenta de la compañía se cierra de un día para otro.

Lo que sí se encontró son **caminos legítimos**: piezas que son libres,
piezas que necesitan atribución, piezas que se pueden comprar con licencia, y
piezas que hay que apagar en la edición que se vende. Eso es lo que sigue.

## La edición pública

`SERGIO_EDICION=publica` (`src/openjarvis/edicion.py`) apaga, para todos los
clientes y sin que ningún otro interruptor lo pueda volver a encender, lo que
es un riesgo personal del dueño y no se vende:

| Pieza | Por qué se apaga en la edición pública |
|---|---|
| Clips de internet y de películas o series con yt-dlp | Los términos de YouTube y de otros sitios prohíben descargar; el clip de una película es del estudio. Alcanza para uso personal bajo riesgo propio; no para un servicio de pago. |
| Canción «con derechos» pedida por nombre | Igual: es una obra con derechos, y el paquete ya avisa que pueden reclamarla. |
| Colecciones de prompts descargadas (GPL-3.0 y repos sin licencia) | GPL-3.0 exige abrir el código derivado, y un repositorio sin licencia no da permiso de uso. En el equipo del dueño es personal; en una nube que se vende, no. |
| Jamendo (clave gratuita de la API) | La clave gratuita es **no comercial**; la música comercial exige su licencia de pago. |
| OpenSky Network | Su licencia es **no comercial** (así lo dice el NOTICE). |

## Resultado de la revisión de dependencias

- **Python** (todas las instaladas en el entorno): todas tienen licencia
  declarada. La única con copyleft es `python-telegram-bot` (LGPL-3.0): se usa
  como biblioteca sin modificarla, que LGPL permite en un producto cerrado si
  se conserva el aviso y se deja reemplazarla. Ninguna es solo no comercial.
- **Web** (npm): 701 MIT, 37 ISC, 17 Apache-2.0, BSD, OFL (letras), MPL-2.0 (3):
  nada que impida vender. MPL-2.0 pide publicar los cambios **a esos archivos**
  si se modifican (no se modifican).
- **No cubierto aquí**: dependencias de las extensiones (`extensions/`),
  programas que se instalan aparte (Blender, FreeCAD, Kdenlive…, GPL/LGPL: se
  descargan de su fuente y no se redistribuyen) y los modelos descargados.

## Piezas con riesgo y qué hacer

| Pieza | Licencia o término | Riesgo vendiéndola | Camino legítimo |
|---|---|---|---|
| **FFmpeg** (el binario que trae `imageio-ffmpeg`) | LGPL/GPL según la compilación | **Alto si se empaqueta en un instalador**: una compilación con x264 es GPL y obliga a ofrecer el código fuente de todo lo que se distribuye junto. | Usar una compilación LGPL (sin `--enable-gpl`) o pedir al cliente que lo instale; en la nube (sin distribuir el binario) la GPL no obliga igual, pero conviene confirmarlo con el abogado. |
| **Gemini, Claude, GPT, DeepSeek vía OpenRouter** | Términos de cada proveedor | **Medio**: revenden acceso. Hay que confirmar por escrito que los términos de OpenRouter y de cada empresa permiten ofrecer sus modelos dentro de un producto propio (revender la API «tal cual» suele estar limitado; integrarla en un producto con valor añadido suele estar permitido). Además, la clave gratuita de Gemini permite que Google use lo enviado. | Solo claves de pago para clientes; leer los términos vigentes; guardar la respuesta por escrito. |
| **ElevenLabs** (voz) | Plan comercial | Medio | Contratar el plan que incluya licencia comercial; la voz es la de la biblioteca de ElevenLabs, no un clon. |
| **Pexels y Pixabay** (video e imágenes) | Su licencia gratuita permite uso comercial; **prohíben** redistribuir el archivo solo o como parte de un servicio de archivos | Bajo si se usan dentro de un video nuevo | Mantener el crédito; no ofrecer una «biblioteca» de esos archivos. |
| **Openverse, ccMixter, Internet Archive, Wikimedia** | Cada archivo con su licencia (CC0, BY, BY-SA…) | Bajo si se respeta la atribución, y **BY-SA** pide que la obra derivada lleve la misma licencia | Ya se filtra por licencias que permiten ganar dinero y se citan los créditos. Mejor aún: BY-SA fuera de la edición pública. |
| **Poly Haven** | CC0 | Ninguno | — |
| **Kimodo / MotionBricks / Audio2Face** | NVIDIA (cada una con su licencia); el checkpoint SMPL-X de Kimodo es **solo investigación** | Alto para el SMPL-X | Ya no se usa SMPL-X. Leer la licencia de cada pieza antes de incluirlas en algo que se vende. |
| **MediaPipe, YuNet, SFace, Whisper, Kokoro, e5** | Apache-2.0 / MIT | Bajo | Mantener los avisos del NOTICE. |
| **FlyWire (conectoma)** | CC BY 4.0 | Bajo: permite uso comercial **con atribución** y aviso de cambios | Ya está en el NOTICE con las citas. |
| **Escalas de salud mental** (PHQ-9, GAD-7, WHO-5, Rosenberg, UCLA-3, PSWQ) | PHQ-9 y GAD-7 son de uso libre (Pfizer); WHO-5 libre con cita; las demás las publican sus autores | **Medio**: cada una tiene condiciones propias y un producto de pago no es una investigación | Revisar autor por autor; pedir permiso por escrito a quien lo pida; la «orientación» de Sergio no es diagnóstico (ya se dice). |
| **Logos de servicios** (Simple Icons) | El archivo es CC0, pero **el logo es marca de su dueño** | Medio | Mostrarlos solo para decir «se conecta con X», sin sugerir aval; si una empresa lo pide, quitarlo. |
| **Nombres de cineastas y creadores** en las fichas de técnica | Marcas y nombres de personas | Bajo mientras no se use su imagen ni se sugiera aval | Ya no se nombran en pantalla; en la edición pública conviene dejar solo la técnica. |
| **«Face ID» y «JARVIS»** | Marcas de Apple y de Marvel | Alto | Ya cambiados: «Visage» (provisional; falta comprobar que se pueda registrar) y sin JARVIS. |
| **Apple, iMessage, ChatGPT, Notion como «referencia de diseño»** | Diseño de otros | Medio con el estilo de iMessage | Es una forma general (burbujas), no un diseño protegido; evitar copiar iconos, textos o animaciones propias. |

## Antes de lanzar

1. Registrar la marca «Sergio» y el nombre «Visage» (búsqueda de
   disponibilidad en EE. UU., UE y Reino Unido; en el nombre «Sergio» habrá
   mucho en uso: puede hacer falta un nombre de producto distinto).
2. Elegir la compilación de FFmpeg y documentarla.
3. Que un abogado lea los términos de OpenRouter, Google, Anthropic, OpenAI,
   ElevenLabs y NVIDIA, y confirme (por escrito) que se puede ofrecer lo que
   Sergio ofrece.
4. Publicar términos de uso, política de privacidad y una página de
   «Licencias de terceros» (el NOTICE lo cubre en parte).
5. Ejecutar la edición pública (`SERGIO_EDICION=publica`) en la nube.
