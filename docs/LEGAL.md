# Sergio y la ley

Revisión del 21 de octubre de 2026. **No es asesoría legal.** Resume las
normas públicas que tocan a un asistente personal como Sergio y lo que se hizo
en el código para cumplirlas. Antes de vender Sergio o abrirlo a otras
personas, consulte a un abogado en Ecuador.

## 1. Lo más importante: uso personal

- **Ecuador (LOPDP, 2021).** El artículo 2 excluye de la ley lo que una
  persona hace con datos en actividades familiares o domésticas. El
  Reglamento lo limita al entorno de familia, amigos o grupo cercano, en
  propiedad privada y sin fines comerciales. La resolución
  SPDP-SPD-2026-0003-R (enero de 2026) dice que **publicar datos** (redes, un
  enlace abierto) sale de la excepción, y que la Superintendencia mira cada
  caso por separado.
- **Unión Europea.** El RGPD (art. 2.2.c) y la Ley de IA (art. 2.10) tampoco
  se aplican al uso puramente personal.
- **Consecuencia.** Mientras Sergio sea su asistente en su casa, casi todas
  las obligaciones de empresa no le alcanzan. Eso cambia si:
  - lo vende o lo ofrece a otras personas;
  - publica lo que Sergio guarda de otras personas;
  - lo usa en un trabajo con empleados o clientes.

## 2. Lo que se revisó y cómo queda

| Tema | Norma | Estado en Sergio |
|---|---|---|
| Caras de otras personas | LOPDP: los datos biométricos son sensibles | Solo se registra a alguien con su consentimiento (`consent=true`, el servidor rechaza sin él). La galería va cifrada (Fernet) y su clave se guarda aparte. A los desconocidos («Persona 2») solo se les recuerda 30 minutos, en memoria, sin guardarlos. |
| Grabar reuniones | COIP art. 178 (violación de la intimidad: grabar o difundir audio ajeno sin consentimiento, 1-3 años) | **Cambiado:** Sergio avisa en **cada** reunión, no una vez al día, que hay que decir a todos que se graba y parar si alguien no está de acuerdo. La excepción para «quien participa» tuvo un intento de reforma en 2021; no se confía en ella. |
| Llamadas a terceros | Ley de IA de la UE art. 50; FCC 2024 (EE. UU.): una voz de IA es «voz artificial» y necesita consentimiento previo | La primera frase de cada llamada a otra persona dice que habla una IA y de parte de quién (`phone/bot.py: greeting`). Las llamadas y los mensajes nunca son automáticos: los inicia el dueño. No llama a números de EE. UU. en masa ni con fines comerciales. |
| Salud y salud mental | LOPDP: los datos de salud son sensibles; no es un dispositivo médico | Nunca es un diagnóstico (lo dice la pantalla). Las líneas de crisis salen al instante. **Nuevo:** se borran correos, teléfonos, cédulas y enlaces antes de enviar algo a la IA (`health/privacy.py: scrub`). Interruptor **«Solo en este equipo»** en Salud mental: con él, ni la lectura de la encuesta ni las preguntas de salud llegan a la IA. La base de salud queda legible solo para su usuario del sistema (0600). |
| Gemini con clave gratuita | Términos adicionales de la API de Gemini, «Servicios no pagados» | Con una clave gratuita, Google puede usar lo que se envía para mejorar sus productos, y personas pueden leerlo (separado de su cuenta). Google pide no enviar datos sensibles por esa vía. Con facturación activada (servicio pagado) no lo usa. **Recomendación:** active la facturación en su proyecto de Google AI Studio, o use «Solo en este equipo» para la salud. Esto también afecta a la cámara y la pantalla que Gemini Live ve. |
| Memoria y cerebro | Seguridad de datos personales | Todo es local. `cerebro.db` queda solo para su usuario (0600), nunca guarda claves y `SERGIO_CEREBRO=0` lo apaga. |
| Análisis de uso | Consentimiento | Desactivado por defecto (`[analytics] enabled = false`). El ranking público también, y su correo nunca sale. |
| Voces | Derecho a la propia imagen y voz | Ninguna voz real se clona: se usan voces de Google o del sistema. |
| Marcas y logos | Uso nominativo; las marcas de terceros piden permiso | Ver `docs/LEGAL-MARCAS.md`: ningún logo ajeno; las universidades solo como texto, con aviso de que no hay relación ni aval. |
| Licencias de software | Apache-2.0, MIT, OFL, GPL | NOTICE completado: letras, modelos de caras, MediaPipe, globo, ECC, OpenSky y USGS. Los repos GPL o sin licencia de la biblioteca de prompts se descargan a su equipo y nunca se copian al repositorio. LidoJS no se usa porque no tiene licencia abierta. |
| Datos de vuelos | Licencia de OpenSky: solo uso no comercial | Uso personal, permitido. Para un producto comercial habría que contratar a OpenSky. Si publica algo hecho con esos datos, cite a OpenSky (está en NOTICE). |
| Mensajes de WhatsApp | Términos de WhatsApp | La vía «Baileys» es una conexión no oficial: no es ilegal, pero WhatsApp puede **bloquear el número**. Lo seguro es la API oficial (WhatsApp Cloud API). Los envíos nunca son automáticos. |
| Imágenes con otros servicios | Términos de cada servicio | Si la clave de Gemini no tiene cuota de imágenes (la gratuita no la tiene), Sergio prueba OpenAI o Hugging Face si hay clave, y si no Pollinations, sin clave. A ese servicio solo viaja la descripción de la imagen, marcada como privada. `SERGIO_IMAGENES_LIBRES=0` lo apaga. No describa a personas reales por su nombre. |
| Videos de YouTube y otros | Derechos de autor y términos de YouTube | Solo use videos suyos o con permiso como referencia de estilo. Sergio no los publica. |
| Video ensayo «como este» | Derechos de autor (películas, noticias, archivo); licencias de Pexels y Pixabay | De la referencia solo se aprende **cómo está editada** (ritmo, tipos de toma, letras, efectos): Sergio nunca descarga ni usa sus imágenes, su música ni sus palabras. Las películas y noticias que salen en esos ensayos son de otros, así que en su lugar van **sus clips**, video libre de Pexels o Pixabay (licencias que permiten cualquier uso, sin atribución obligatoria) o imágenes que hace Sergio. Los efectos de sonido y la música de fondo los genera Sergio. El guion no inventa citas de personas reales ni cifras. El video nunca se publica sin su permiso. |

## 2 bis. Cobrar por Sergio (planes de pago)

- Sergio **nunca toca datos de tarjeta**: el pago ocurre en la página del
  procesador (un enlace de pago, `SERGIO_CHECKOUT_<PLAN>`) y vuelve una clave
  de licencia firmada que se comprueba sin conexión (`tiers.py`). Así la
  norma de seguridad de tarjetas (PCI DSS) la cumple el procesador.
- Precio claro antes de pagar, en la moneda del cliente y **con los impuestos
  incluidos** (IVA en Ecuador y la UE; en la UE el comprador paga el IVA de su
  país). Lo más sencillo es un procesador que actúe como **vendedor oficial**
  (*merchant of record*, por ejemplo Paddle o Lemon Squeezy) o activar el
  cálculo de impuestos del procesador.
- Cancelación fácil y sin trabas, y aviso antes de cada renovación. En la UE el
  cliente puede desistir en 14 días (en servicios digitales, salvo que acepte
  empezar de inmediato y lo reconozca); en Ecuador rige la Ley Orgánica de
  Defensa del Consumidor (información veraz, factura, derecho de retracto en
  compras a distancia). Hacen falta términos de servicio y política de
  reembolso publicados.
- Factura electrónica (SRI en Ecuador) cuando el comprador la pida.
- Los límites de uso solo se aplican en el servicio alojado
  (`SERGIO_PLANES_ACTIVOS=1`); el código abierto en el equipo del dueño no se
  bloquea a sí mismo.

## 3. Lo que no se puede resolver con código (decisión suya)

1. **Facturación de Gemini.** Es la forma de que Google no use ni revise lo
   que envía. Se activa en aistudio.google.com, en su proyecto.
2. **Publicar o vender Sergio.** Si lo hace:
   - hace falta una política de privacidad y unos términos;
   - si trata datos de otros a escala, un delegado de protección de datos
     (LOPDP);
   - el aviso de IA de la Ley de IA europea si hay usuarios en la UE (desde el
     2 de agosto de 2026);
   - revisar los diseños «idénticos» a ChatGPT y Notion, porque copiar el
     aspecto de un producto ajeno puede ser competencia desleal o imitación de
     imagen comercial (*trade dress*), aunque no se usen sus logos;
   - registrar la marca «Sergio» para software en el SENADI, después de buscar
     marcas parecidas.
3. **«JARVIS».** Es un personaje de Marvel (Disney). Sergio solo toma la idea
   de un mayordomo cortés: no usa ese nombre a la vista ni lo imita. Debe
   seguir así.
4. **Personas en casa.** Si alguien no quiere que Sergio vea su cara o grabe
   su voz, se respeta:
   - se borra a la persona en Caras;
   - se silencia el micrófono;
   - no se usa «Sergio ve» mientras esa persona esté.

## Fuentes

- Términos adicionales de la API de Gemini (Servicios no pagados):
  https://ai.google.dev/gemini-api/terms
- LOPDP, artículo 2 y excepción doméstica:
  https://www.lexis.com.ec/blog/otros/sobre-la-ley-de-proteccion-de-datos-personales-lopdp
- Resolución SPDP sobre el ámbito familiar o doméstico (2026):
  https://nmslaw.com.ec/blog/2026/02/02/spdp-tratamiento-datos-personales-familiar-domestico-ecuador/
- Datos biométricos como datos sensibles (Superintendencia):
  https://www.expreso.ec/actualidad/empleadores-ecuador-deben-evitar-datos-biometricos-dice-superintendencia-235909.html
- COIP, artículo 178, y la reforma de 2021:
  https://primicias.ec/noticias/politica/proteccion-intimidad-censura-reformas-coip
  y https://www.primicias.ec/noticias/politica/fiscalia-reforma-coip-indice-impunidad
- Ley de IA de la UE, artículo 50 (aplica desde el 2 de agosto de 2026):
  https://www.cooley.com/news/insight/2026/2026-08-03-eu-ai-act-transparency-obligations-take-effect-2-august-2026
- FCC, voces de IA en llamadas (2024):
  https://huntonak.com/privacy-and-information-security-law/fcc-issues-declaratory-ruling-that-tcpa-applies-to-ai-generated-voice-calls
- Licencia de datos de OpenSky: https://en.wikipedia.org/wiki/OpenSky_Network
  (términos en opensky-network.org)
