# Seguridad de Sergio

Ningún programa conectado a internet es imposible de hackear. Ni Apple ni los
bancos lo prometen, y Sergio tampoco. Lo que sí hace Sergio es cerrar todo lo
que se puede cerrar y comprobarlo con pruebas.

## Qué protege a Sergio

| Capa | Qué hace |
|---|---|
| Puerta de entrada | Desde fuera (túnel o red) todo responde 403 salvo entrar a una cuenta y los avisos firmados de pagos. Probado ruta por ruta. |
| Cuentas | Contraseñas con scrypt, códigos y sesiones guardados con HMAC, freno de intentos, antifraude y llaves de acceso con la cara del dispositivo. |
| Secretos | Claves solo en `~/.openjarvis/sergio.env` (0600 en POSIX; ACL del usuario actual en Windows). Al arrancar, Sergio vuelve a dejar privados sus archivos secretos si algo los abrió (`security/permisos.py`). |
| Cifrado | Claves de IA de clientes, notas y encuestas de salud (incluida salud mental), memoria de conversaciones, recordatorios, memoria y mensajes de los Nodes, sus secretos y galería de caras con AES-256-GCM, una clave derivada por propósito y atada a su fila (`security/boveda.py`). Libro de pagos sellado con HMAC encadenado (`docs/PAGOS.md`). |
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

- **El repositorio de trabajo de GitHub es privado.** Una consulta pública sin sesión no debe poder abrirlo. Sergio nació de OpenJarvis (Apache-2.0), y esa licencia sigue permitiendo copiar lo que ya se publicó.
- **Para proteger lo nuevo:**
  1. Mantener el repositorio **privado** y revisar quién tiene acceso. Si cambia su visibilidad, su PC necesita permiso para seguir actualizando (`gh auth login` en Ubuntu); si no, el comando de actualizar fallará.
  2. Registrar la marca «Sergio» y el logo en el SENADI (Ecuador). El nombre y la marca sí se pueden proteger aunque el código haya sido abierto.
  3. Para clientes: que usen Sergio desde su servidor, con cuenta, y no instalen el código. Lo que nunca sale de su servidor no se puede copiar.

## La bóveda: qué está cifrado y qué no (2 nov. 2026)

El dueño pidió «encriptar todo, nivel bancario». Esto es lo que hay de verdad:

**Cifrado en reposo (AES-256-GCM, el mismo tipo de cifrado que usan los bancos):**
- notas del día y etiquetas de Salud,
- encuestas de salud mental: respuestas, puntajes y lectura,
- memoria de las conversaciones (engramas del cerebro),
- galería de caras (`faces/book.py`),
- claves de IA de cada cliente.

Cada valor lleva su propia clave derivada (HKDF) del propósito (`salud`, `memoria`…), un
valor aleatorio nuevo cada vez y el lugar al que pertenece: un valor copiado a otra fila no
abre. Lo que estaba guardado en claro antes se sella solo al abrir Sergio. Una prueba
comprueba que el texto privado no aparece en el archivo del disco.

**No está cifrado campo por campo, a propósito:**
- los números de salud (pasos, pulso…): la base de datos los suma y promedia, y para eso
  tiene que leerlos. Quedan protegidos por permisos 0600 y por el cifrado del disco.
  **Active BitLocker (Windows), FileVault (Mac) o LUKS (Linux).** Es lo que de verdad cierra
  esta puerta.
- cuentas (correo, teléfono): se usan para buscar y entrar; contraseñas y códigos ya van con
  scrypt y HMAC.

**Honestidad sobre «nivel bancario»:**
- El cifrado es del mismo tipo que usan los bancos. Un banco, además, tiene auditorías
  externas (PCI DSS, SOC 2, ISO 27001), módulos de hardware para las claves, personal de
  seguridad y planes de respuesta. Sergio no tiene nada de eso todavía y **no debe
  anunciarse como «nivel bancario» ni «inhackeable»** hasta tener una auditoría externa.
- La clave maestra está en `~/.openjarvis/clave_maestra` (0600) o en `SERGIO_CLAVE_MAESTRA`.
  Quien se lleve el disco **y** la clave lo lee todo. En un servidor, la clave va en un
  gestor de secretos y no en el mismo disco.
- Perder la clave maestra pierde lo que sella: haga copia de ella en un lugar aparte.

**Falta para la nube (cuando Sergio sirva a clientes):**
1. Una clave por cliente (hoy hay una por equipo).
2. La clave en un gestor de secretos o un módulo de hardware (KMS), con rotación.
3. TLS 1.2+ siempre y HSTS en el dominio público; copias de seguridad cifradas.
4. Registro de accesos a datos sensibles, borrado verificable de la cuenta y exportación.
5. Prueba de penetración y auditoría de un tercero antes de lanzar.

## El llavero: versiones, rotación y frase (3 nov. 2026)

El dueño pidió cifrado «nivel Vertu o bancario». Vertu es una marca de teléfonos
de lujo, no un estándar de seguridad; «bancario» sin certificar tampoco lo es. Lo que
Sergio hace ahora es lo mismo que hace un servicio de claves de un banco
(KMS), en pequeño:

- **Versiones de clave.** Cada valor cifrado lleva el id de su clave
  (`v2:<id>:…`). `sergio boveda rotar` crea una clave nueva para todo lo que se
  guarde desde ese momento; lo anterior sigue abriéndose con su clave. Los
  valores de antes del llavero (`v1:`) abren con la clave original.
- **Llavero cifrado con frase.** `sergio boveda proteger` cifra el propio
  llavero (AES-256-GCM) con una clave sacada de una frase por scrypt
  (N=2^17, r=8, p=1: unos 128 MB por intento, para que adivinarla sea lento). El
  disco ya no guarda ninguna clave usable; el servidor necesita la frase en
  `SERGIO_FRASE_MAESTRA` para arrancar. Si la frase vive en el mismo disco, la
  ganancia es poca: debe ir en un gestor de secretos o escribirse al arrancar.
- **El libro de pagos** se firma siempre con la primera clave, así su cadena se
  sigue comprobando después de rotar.
- `sergio boveda estado` dice la clave activa, cuántas hay y si hay frase.

Lo que sigue sin existir: certificación (PCI DSS, SOC 2, ISO 27001), módulo de
hardware (HSM) y auditoría externa. Hasta tenerlos no se dice «nivel bancario».
