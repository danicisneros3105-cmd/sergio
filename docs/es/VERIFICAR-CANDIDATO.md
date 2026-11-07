# Verificar el candidato de Sergio

Fije el commit que se pretende distribuir. Las pruebas y la firma deben
corresponder a ese mismo candidato; si cambia el código, repita las que
afecte el cambio. Una compilación local, un simulador o un informe sin la
versión comprobada no acredita el lanzamiento.

1. Ejecute **CI**, **Frontend CI** y **Sergio release smoke** para ese commit.
   Los dos primeros cubren el backend y el build limpio. El último compila
   desde el lock de npm y usa Chromium y WebKit en Windows, macOS y Linux.
   Comprueba el manifiesto, los iconos, el worker, el acceso y la reapertura
   de una tarea con una API de prueba. No necesita cuentas ni claves externas.
2. Prepare una instalación HTTPS de preproducción con un dueño y una cuenta
   aprobada de prueba. Pruebe registro y verificación, acceso, cierre y
   revocación, dos cuentas, y recuperación tras reconectar. El modo personal
   del dueño incluye Cowork, el navegador persistente y el escritorio remoto.
   En un servidor compartido las cuentas de cliente tienen el chat y las
   rutas habilitadas para clientes; no se debe vender acceso al escritorio
   ni a las herramientas del dueño.
3. Haga el recorrido de abajo en equipos reales. Registre modelo del equipo,
   versión de SO y navegador, commit, resultado y hora de cada intento.
   Repita con una lectura que no coincida y una que requiera iniciar sesión.
   Use una página de ensayo y una cuenta sin datos privados.
4. Para Windows de escritorio, siga
   [el procedimiento del instalador](LANZAMIENTO-WINDOWS.md): VM limpia,
   instalación, arranque, actualización, firma y verificación del SHA-256
   del artefacto firmado. Un instalador que clona un repositorio privado se
   puede usar para la beta autorizada, no como descarga pública.
5. Solo habilite funciones externas que pasen sus pruebas reales de
   preproducción. Use cuentas de prueba para conectores y voz y el modo de
   pruebas del procesador para pagos. Verifique también el aviso de privacidad,
   los permisos y el proceso de eliminación aplicable a esa instalación.

| Equipo real | Recorrido mínimo antes de anunciar soporte |
|---|---|
| iPhone e iPad | Añadir desde Safari, iniciar sesión y probar el retorno desde pantalla de inicio, con el equipo bloqueado y desbloqueado. |
| Android | Instalar desde el navegador compatible, abrir desde el icono y repetir con el navegador cerrado. |
| Windows | Probar el acceso web y, por separado, la app instalada desde Inicio, los permisos locales y el actualizador. |
| macOS | Probar el cliente web, acceso y permisos del navegador. Verificar cualquier función nativa que se anuncie por separado. |

En cada equipo, lance una lectura con un texto esperado, cierre la ventana,
vuelva a abrir, autentíquese si se solicita y compruebe la evidencia. El
servidor debe permanecer activo. Para probar una creación de texto en Cowork,
pida guardar un acta en una ruta absoluta de ensayo con un literal conocido;
el paso solo se confirma si la herramienta lo escribió y volvió a leer ese
mismo archivo con el literal. Esto no mide la calidad de un video o documento.
