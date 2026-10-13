# Sergio: diseño, identidad y aplicaciones profesionales

Esta actualización parte de `main` e1396e7, conserva los cambios de Claude en
Nodes, voz Live, worklet y reconocimiento facial, y añade cambios revisados de
Codex. Los programas externos conservan sus aplicaciones completas; el catálogo
no los sustituye por imitaciones reducidas ni significa que estén instalados.

## Qué cambia

- **Estudio** reúne 32 herramientas, búsqueda, categorías, detección real en PATH
  del servidor, apertura mediante el compañero Windows e instalador selectivo
  WinGet. Las herramientas de terminal no tienen un botón que finja abrir ventanas.
- `/studio`, `/developer` y el antiguo `/creator` abren la misma sección. Rostros
  también tiene un acceso en la barra. Anatomy no es una sección.
- El diseño reutiliza el shell, la tipografía y los personajes del equipo:
  superficies neutras, azul claro, menos gradientes y ruido, personajes de fieltro
  más suaves. Las vistas respetan movimiento reducido y tamaños móviles.
- Los hologramas tienen luz estable, superficies redondas con iluminación
  continua y polos cerrados. La esfera anterior perdía caras en el polo superior
  por triángulos de área cero: está corregido. Se conservan los materiales de los
  modelos, las medidas, la física y los controles existentes.

## Identidad: reconocer y autorizar

Una webcam RGB **no equivale a Face ID**. TrueDepth usa profundidad e infrarrojos;
Apple protege sus representaciones con hardware. No se atribuyen esas garantías,
ni una tasa de errores de uno en un millón, al modelo de la webcam de Sergio.

El escaneo existente sigue sirviendo para reconocer personas consentidas. Las
muestras borrosas no cuentan como coincidencia fuerte; los ángulos no finitos
se descartan y un escaneo incompleto no guarda muestras ni una malla válida.

La aprobación del compañero y de su API de control usa una hoja con la acción
visible y **Windows Hello**. Solo el resultado del sistema permite continuar;
cancelar, fallar o agotar el tiempo deniega. Antes de terminar la inicialización
el control deniega las acciones. Se conserva la política estricta de permisos.
Windows Hello puede usar rostro con hardware compatible, huella o PIN: no se
presenta todo resultado de Hello como un reconocimiento facial.

La galería se cifra con Fernet. La creación de claves es exclusiva, los archivos
se escriben de forma atómica y las galerías antiguas válidas se cifran al leerlas.
Una clave perdida no se regenera para una galería cifrada ni borra su contenido.
La clave de la galería es un archivo privado, **no un Secure Enclave**.

No se ha probado aquí una autenticación física con Windows Hello ni se ha
certificado biometría. Esa comprobación debe hacerse en el equipo Windows del
dueño con Hello configurado; los tests del contrato y de fallo seguro son portables.

## Anatomy, interna

Adaptación de [wheresryan22/anatomy](https://github.com/wheresryan22/anatomy), MIT,
commit `240a9bf7c50cc6226148762a1017466fcbc08523`. El kit, ejemplos fuente,
referencias, scripts y créditos están incluidos en `skills/bundled/anatomy`.
Las páginas generadas y el material multimedia de ejemplo no se incluyen.

La política corta se incorpora a los agentes y a la voz Live para aplicar sus
principios en cada creación visual. Las instrucciones detalladas están disponibles
como `skill_anatomy`, interna, y los recursos se cargan cuando hacen falta. No se
añade una página ni se envía el kit entero al modelo en cada turno.

## Aplicaciones completas y estado de integración

| Trabajo | Herramientas | Qué está implementado |
|---|---|---|
| Código | VSCodium, Git, GitHub CLI, Windows Terminal, PowerToys, uv, ripgrep, fd, bat, just, Node.js | Catálogo, detección, instalador WinGet; abrir las aplicaciones con ventana en Windows |
| Arquitectura | FreeCAD, Blender, LibreCAD | Acceso a las aplicaciones completas, instalador y alias del compañero; se conserva el flujo Blender/DXF existente |
| BIM | Bonsai, antes BlenderBIM, de IfcOpenShell | Entrada y guía de extensión; instalar Blender no se confunde con tener Bonsai activo |
| Creatividad | ArtCraft, PhotoCraft, LightCraft, VectorCraft, FilmCraft, EffectCraft, DesignCraft, PdfCraft, WordCraft, SoundCraft, DeckCraft, CADCraft, GridCraft | Catálogo, fuentes, releases y apertura de aplicaciones instaladas; varias aplicaciones del upstream están en alpha o desarrollo |
| Vídeo | Kdenlive | Aplicación completa como complemento de FilmCraft, instalación y apertura |
| Lienzos | OpenDesign de Clawnify | API real: listar, crear, leer campos, rellenar plantillas, editar y consultar marcas; editor completo en su propio runtime |
| LidoJS | lidojs/canva-clone | Referencia revisada; no redistribuido ni habilitado: licencia no declarada y paquetes @lidojs por verificar |
| Mercados | shiyu-coder/Kronos | Adaptador local con validación OHLCV, fechas, límites, proceso separado y pesos locales; produce escenarios, nunca órdenes de bolsa |

**Esto no certifica todas las funciones de esos programas ni significa que se
ejecutaron en el PC del dueño.** FreeCAD, Bonsai, LibreCAD, ArtCraft y Kdenlive
siguen necesitando sus instalaciones. Los modelos de ArtCraft pueden requerir
cuentas o créditos externos. Kronos requiere su entorno y pesos; no se ha medido
su precisión financiera ni ejecutado inferencia real de pesos en esta revisión.

OpenDesign se conecta solo a un servicio loopback configurado por el dueño;
no sigue redirecciones, limita tamaños y no permite un destino externo arbitrario.
El adaptador sigue el contrato de su repo en
`a0ea785a3be38f61a944571c7a7f72c2ce7d2c2f`. Kronos usa el código de
`67b630e67f6a18c9e9be918d9b4337c960db1e9a` y bloquea descargas implícitas durante
el cálculo. Los runtimes se preparan por separado para no cargar el chat con ellos.

## Uso y actualización

Actualización en PowerShell, sin restablecer la rama ni descartar commits:

```powershell
wsl -d Ubuntu -- bash -lc "cd ~/sergio && git fetch origin main && bash scripts/actualizar-sergio.sh main"
```

En Estudio, seleccione las aplicaciones con casilla, pulse **Preparar instalador**
y ejecute el archivo descargado en PowerShell. No se instalan en el servidor al
descargarlo. Las aplicaciones ArtCraft sin paquete WinGet revisado tienen sus
releases oficiales enlazadas.

Para OpenDesign, en Ubuntu dentro de Sergio:

```bash
bash scripts/preparar-integraciones.sh opendesign
bash scripts/preparar-integraciones.sh iniciar-opendesign
```

El editor usa el puerto 5178 y su API el 8787. El script obtiene el repo completo,
comprueba el commit y usa el lockfile, tests y build del upstream. Deje esa terminal
abierta. Se prepara el runtime de Kronos con el mismo script y el argumento `kronos`;
coloque sus pesos en los directorios que indica antes de pedir una previsión.

Ejemplos con condiciones concretas:

- «Abra VSCodium»: usa la aplicación instalada y los permisos del compañero; no
  afirma éxito si no está disponible. Git, uv y ripgrep se utilizan en terminal.
- «Cree un lienzo cuadrado llamado Mi marca»: con OpenDesign iniciado, el adaptador
  crea un diseño real de 1080 × 1080. Si no está iniciado, devuelve un error claro.
- «Rellene la plantilla con estos títulos»: necesita el id y los nombres reales
  de sus campos; se puede guardar una variante sin publicar nada.
- «Calcule un escenario para estas velas»: Kronos requiere datos OHLC coherentes,
  al menos 16 observaciones, fechas con zona horaria y calendario futuro explícito.
  Sin pesos locales no devuelve números inventados.

## Validación

- 720 pruebas de escritorio aprobadas, 4 omitidas.
- 526 pruebas de backend, rostros, skills, Nodes y rutas relacionadas aprobadas,
  2 omitidas. Cuatro pruebas live que requieren Ollama y skills personales se
  excluyeron; no se presentan como aprobadas.
- 161 pruebas frontend aprobadas; TypeScript y compilación de producción correctos.
- 32 pruebas puras del kit Anatomy aprobadas. Los checks que requieren Chrome/CDP
  no se certifican; se hicieron capturas offline con el frontend real y QtWebEngine.
- Ruff: análisis y formato de `src/` y `tests/` correctos.
- Configuración del SDK Gemini Live validada para las nuevas herramientas, sin
  llamar a un proveedor real. Catálogo del modelo completo en menos de 4k caracteres.
- Capturas offline con datos de prueba: Estudio a 1440 px en claro y a 390 px
  en oscuro, Nodes a 1440 px en claro y Rostros a 1440 px en oscuro;
  hoja nativa de consentimiento y hologramas renderizados con su código real.
  No se certifican todas las vistas móviles ni un tiempo de respuesta medido.

Fuentes: [Face ID, Apple](https://support.apple.com/en-us/102381),
[WinRT desktop consent, Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/userconsentverifierinterop/nn-userconsentverifierinterop-iuserconsentverifierinterop),
[ArtCraft apps](https://getartcraft.com/apps),
[OpenDesign](https://github.com/clawnify/OpenDesign),
[Kronos](https://github.com/shiyu-coder/Kronos),
[Bonsai](https://bonsaibim.org/).
