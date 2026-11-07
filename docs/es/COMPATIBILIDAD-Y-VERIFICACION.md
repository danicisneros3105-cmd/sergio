# Compatibilidad y comprobación de tareas

La interfaz instalable de Sergio es un cliente del servidor. Para acceder
desde otro equipo, use la dirección HTTPS de su instalación e inicie sesión.
Si el servidor está en su PC, ese PC debe permanecer encendido y conectado
para ejecutar las tareas remotas. Una ejecución del servidor no depende de
que la pestaña del dispositivo siga abierta.

| Dispositivo | Ruta de instalación que se debe comprobar |
|---|---|
| iPhone y iPad | Abrir en Safari y usar Compartir → Añadir a pantalla de inicio. |
| Android | Abrir en un navegador compatible y usar la opción de instalación del navegador. |
| Windows | Usar Sergio Escritorio para las funciones locales, o instalar el cliente desde un navegador compatible. |
| macOS y Linux | Usar el cliente en un navegador compatible. |

La instalación desde el navegador no concede acceso a la pantalla, archivos
o controles de sistema de otros dispositivos. Las acciones que necesitan
Sergio Escritorio requieren el equipo correspondiente conectado.

- Una lectura con texto esperado se confirma solo cuando ese texto figura en
  la lectura del sitio. El resultado registra la URL, el texto buscado y un
  extracto. Si falta la sesión, hay un error o no aparece el texto, Sergio
  indica el motivo. Una vigilancia que vence sin coincidencia conserva ese
  resultado.
- Cowork admite comprobar lecturas mediante `URL | texto exacto`. Un
  «TERMINADO» del modelo sin evidencia de la herramienta queda sin verificar.
  Los pasos que dependan de ese resultado no se declaran listos.
  El navegador de Cowork se habilita con `SERGIO_COWORK_PERSONAL_BROWSER=1`
  solo en una instalación personal: usa un perfil persistente del anfitrión
  y debe quedar desactivado en servidores compartidos.
- Escritorio comprueba la existencia de las rutas de archivo que reconoce en
  el criterio del paso o en su resultado. Existencia no equivale a validar
  el contenido ni la calidad del archivo.

Antes de anunciar soporte para un dispositivo, probar allí: instalar,
iniciar sesión, lanzar una tarea, cerrar el cliente, volver a abrir y
verificar el resultado; repetir con una tarea bloqueada y otra sin
coincidencia. Probar por separado permisos, notificaciones y funciones de
escritorio. Una prueba de agente de usuario no reemplaza este recorrido.
