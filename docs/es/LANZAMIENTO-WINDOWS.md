# Candidato de lanzamiento de Sergio para Windows

El canal previsto es el instalador Sergio para Windows + Ubuntu en WSL2.
El empaquetado Tauri heredado queda fuera de esta distribución y no instala
ni busca actualizaciones de OpenJarvis. Las acciones antiguas de publicación
de Tauri y PyPI son para el proyecto original.

## Construir

Desde la raíz del repositorio, con NSIS y `sha256sum`:

```bash
bash scripts/build-instalador.sh 1.0.2
```

Produce `dist/sergio-windows/Sergio-Instalador.exe` sin firmar y
`SHA256SUMS.txt`. El candidato no sobrescribe el ejecutable histórico.
Tras firmar, vuelva a calcular la suma sobre el archivo firmado.

## Validar antes de distribuir

1. Ejecute la instalación en una VM Windows 11 limpia con Ubuntu en WSL2,
   una cuenta de Ubuntu inicializada y systemd. Para la beta privada, la
   cuenta de GitHub debe tener acceso al repositorio.
2. Verifique que la app abre desde Inicio, completa una conversación con un
   modelo configurado, recupera su historial tras reiniciar y puede actualizarse.
   Compruebe también que una actualización con cambios locales se detiene,
   que la interfaz refleja un error de actualización y que permite reintentar.
3. Pruebe cada servicio incluido en la oferta con una cuenta de prueba:
   autorización y revocación de conectores, voz real, exportación de video y,
   si se ofrecen cobros, checkout y notificación del procesador en sandbox.
4. Requiera comprobaciones de CI en verde y firme el instalador para
   distribución. No distribuya como instalador público una copia que dependa
   del acceso privado a GitHub: hace falta un canal propio de descargas.

El instalador no reemplaza la configuración de WSL ni cambia los permisos
del usuario de Ubuntu. El instalador y la app necesitan verificarse en Windows;
la compilación del frontend por sí sola no acredita una instalación.

## Requisitos de privacidad del entorno público

- Verifique en HTTPS registro, inicio, cierre, caducidad y revocación. Pruebe que
  dos cuentas no ven los datos de la otra y que volver atrás no reabre la sesión.
  La separación local no cifra los datos frente a alguien con acceso al perfil
  del navegador. Utilice perfiles del sistema distintos en equipos compartidos.
- Termine el aviso público con la identidad y contacto del responsable,
  plazos de conservación por tipo de dato y un canal verificado para ejercer
  derechos. Pruebe exportación, corrección y borrado antes de prometerlos.
- En registro abierto, las cuentas nuevas pasan por correo; SMS y OAuth
  autentican cuentas existentes. Configure y pruebe el correo de verificación
  del entorno de producción.
