# ¿Puede el Face ID de Sergio desbloquear el PC o el Mac?

Respuesta corta: **no de forma segura con una webcam normal**, y por eso Sergio
no lo hace.

- **Windows.** La pantalla de inicio solo acepta credenciales de un
  «proveedor de credenciales» del sistema. El reconocimiento facial de Windows
  Hello exige una **cámara infrarroja** compatible; Microsoft dice que no
  funciona con webcams normales. Un proveedor propio con webcam RGB se podría
  engañar con una foto o un video y tendría que guardar su contraseña de
  Windows: no lo instalamos.
- **Mac.** El inicio de sesión moderno (con Touch ID) no admite complementos de
  terceros; los complementos de autorización usan una ruta antigua, frágil
  entre versiones de macOS y que obliga a entregar la contraseña.

Lo seguro que sí hay:

1. **Windows:** una webcam con infrarrojos «Windows Hello» (externa si su PC no
   la trae) y activarla en Configuración → Cuentas → Opciones de inicio de
   sesión. Sergio ya usa Windows Hello para confirmar acciones sensibles.
2. **Mac:** Touch ID o «Desbloquear con Apple Watch».
3. El Face ID de Sergio sigue sirviendo para Sergio: reconocerle y desbloquear
   la app, con su código de respaldo.
