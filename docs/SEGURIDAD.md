# Seguridad de Sergio

Ningún programa conectado a internet es imposible de hackear. Ni Apple ni los
bancos lo prometen, y Sergio tampoco. Lo que sí hace Sergio es cerrar todo lo
que se puede cerrar y comprobarlo con pruebas.

## Qué protege a Sergio

| Capa | Qué hace |
|---|---|
| Puerta de entrada | Desde fuera (túnel o red) todo responde 403 salvo entrar a una cuenta y los avisos firmados de pagos. Probado ruta por ruta. |
| Cuentas | Contraseñas con scrypt, códigos y sesiones guardados con HMAC, freno de intentos, antifraude y llaves de acceso con la cara del dispositivo. |
| Secretos | Claves solo en `~/.openjarvis/sergio.env` (0600). Al arrancar, Sergio vuelve a dejar privados sus archivos secretos si algo los abrió (`security/permisos.py`). |
| Cifrado | Claves de IA de clientes con AES-256-GCM. Libro de pagos sellado con HMAC encadenado (`docs/PAGOS.md`). |
| Navegador | CSP con `frame-ancestors 'self'`, `object-src 'none'` y `base-uri 'self'`, HSTS, nosniff, Referrer-Policy y Permissions-Policy. Sin CORS para sitios ajenos. El servidor no dice qué programa es. |
| Errores | Desde fuera solo una frase. El detalle técnico se ve solo en el PC del dueño. |
| Datos de fuera | Los feeds RSS y las listas de respaldo no pueden traer DOCTYPE ni entidades XML (`security/safe_xml.py`). |
| Dependencias | Revisadas con pip-audit y npm audit (27 oct. 2026: las de la web en 0; las de Python en 0 salvo setuptools, que fija torch y solo afecta al instalar). |

## Cómo se revisó (27 oct. 2026)

- **Historial completo del repositorio:** ninguna clave real filtrada. Solo hay claves falsas de las pruebas.
- **bandit:** 0 hallazgos graves de confianza alta.
- **Ataque desde fuera:**
  - Cada ruta sensible responde 403.
  - Salir de la carpeta del servidor está bloqueado.
  - Un sitio ajeno no obtiene permiso CORS.
  - Un aviso de pago de más de 256 KB se rechaza (413).

## Copias del código

- **El repositorio de GitHub es público.** Cualquiera puede leer y copiar lo que está ahí. Sergio nació de OpenJarvis (Apache-2.0), y esa licencia permite copiar lo que ya se publicó.
- **Para que nadie copie lo nuevo:**
  1. Hacer el repositorio **privado**. En GitHub: Settings → General → Danger Zone → Change visibility. Antes, su PC necesita permiso para seguir actualizando (`gh auth login` en Ubuntu); si no, el comando de actualizar fallará.
  2. Registrar la marca «Sergio» y el logo en el SENADI (Ecuador). El nombre y la marca sí se pueden proteger aunque el código haya sido abierto.
  3. Para clientes: que usen Sergio desde su servidor, con cuenta, y no instalen el código. Lo que nunca sale de su servidor no se puede copiar.
