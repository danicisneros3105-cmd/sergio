# Planes y licencias

Sergio es un fork de OpenJarvis con licencia Apache 2.0. Todo lo que corre en
su equipo es gratis y seguirá siéndolo. Los planes de pago cobran por
**servicios encima del código**, nunca por funciones del programa local.

## Los cinco planes

| Plan | Precio | Qué agrega |
|---|---|---|
| **Free** | $0 para siempre | Asistente completo y local, Cowork, plugins, razonamiento a fondo, visión, voz, copias cifradas, sincronización con su propio almacenamiento y acceso desde el teléfono |
| **Pro** | $12 al mes | Sincronización alojada (sin configurar almacenamiento), skills y plugins premium, canal de actualizaciones anticipadas |
| **Dev** | $24 al mes | Todo lo de Pro, más APIs propias en los Nodes (la clave queda solo en su equipo) |
| **Teams** | $29 por usuario al mes | Varios usuarios con roles (RBAC), inicio de sesión único (SSO), exportación de auditoría |
| **Enterprise** | $99 por usuario al mes | Despliegue en sus servidores (on-prem), soporte dedicado con SLA |

Véalos en la terminal con `sergio planes`.

## Paquetes por especialidad

Usan las mismas licencias que los planes, con otro precio y otro enfoque.
Se emiten con `--paquete` y `sergio licencia estado` muestra su nombre.

| Paquete | Precio | Plan que activa | Para |
|---|---|---|---|
| `power` · Power users | $12 al mes | Pro | Quien automatiza su día |
| `vfx-studio` · VFX Studio | $19 al mes | Pro | Artistas 3D, motion y video |
| `multicanal` · Multi-channel | $39 al mes | Teams | Negocios que atienden por varios canales |
| `privacidad` · Privacy Enterprise | $99 por usuario al mes | Enterprise | Organizaciones que no sacan datos de su red |

```bash
sergio licencia emitir pro --paquete vfx-studio --titular "Estudio Norte" --dias 31
```

Los textos de venta de cada paquete están en `marketing/planes-de-nicho.md`.

## Qué controla el plan

Cada función de pago tiene un nombre en `openjarvis/tiers.py` (`FEATURES`).
El código pregunta `has_feature("premium_skills")` o llama a
`require("premium_skills")`, que da un mensaje claro si falta el plan.

| Función | Plan mínimo | Dónde se comprueba hoy |
|---|---|---|
| `premium_skills` | Pro | `sergio plugin instalar` con plugins marcados `"premium": true` en el índice |
| `hosted_sync` | Pro | Reservado para cuando exista el servidor de sincronización alojada |
| `early_updates` | Pro | Reservado para el canal de actualizaciones |
| `multi_user`, `sso`, `rbac`, `audit_export` | Teams | Reservados |
| `on_prem`, `sla_support` | Enterprise | Reservados (son servicios, no código) |

Las funciones que no están en esa lista son gratis: `has_feature` devuelve
`True` para todas ellas.

## Cómo funciona una licencia

Una licencia es un texto firmado con Ed25519:

```
sergio-lic-v1.<datos en base64>.<firma en base64>
```

Los datos son `plan`, `seats` (puestos), `holder` (titular), `issued` y
`expires`. Sergio la comprueba **sin conexión** con la clave pública, así que
no hay que llamar a ningún servidor ni enviar datos del usuario. Si alguien
cambia una letra de los datos, la firma deja de valer. Al vencer, el equipo
vuelve solo al plan Free.

Para el cliente:

```bash
sergio licencia activar sergio-lic-v1.…   # la guarda en ~/.openjarvis/license.json (permisos 600)
sergio licencia estado                    # plan, titular, vencimiento y funciones
sergio licencia quitar                    # vuelve a Free
```

## Para vender (lo hace el dueño, una sola vez)

1. **Crear las claves de firma**

   ```bash
   sergio licencia generar-claves
   ```

   La clave privada queda en `~/.openjarvis/license-issuer.key` (permisos
   600) y el comando nunca sobrescribe una que ya exista. Guarde una copia
   fuera del equipo, por ejemplo cifrada con `sergio respaldo`. **Nunca la
   suba al repositorio.**

2. **Publicar la clave pública.** Copie la clave pública que imprime el
   comando en `OFFICIAL_PUBLIC_KEY` de `src/openjarvis/tiers.py`. Para
   probar, también sirve la variable `SERGIO_LICENSE_PUBKEY`. La clave
   pública no es secreta.

3. **Crear las páginas de pago en Stripe.** En el panel de Stripe cree un
   *Payment Link* por plan y póngalos en estas variables:

   ```bash
   SERGIO_CHECKOUT_PRO=https://buy.stripe.com/…
   SERGIO_CHECKOUT_TEAMS=https://buy.stripe.com/…
   SERGIO_CHECKOUT_ENTERPRISE=https://buy.stripe.com/…
   ```

   Con ellas, `sergio planes mejorar pro` abre la página de pago.

4. **Emitir la licencia después de cada pago**

   ```bash
   sergio licencia emitir pro --titular "Nombre del cliente" --dias 31
   sergio licencia emitir teams --titular "Empresa" --puestos 8 --dias 365
   ```

   Envíe al cliente el texto que imprime. Más adelante esto se puede
   automatizar con un webhook de Stripe (`checkout.session.completed`) que
   llame a `openjarvis.tiers.issue(...)`. Ese servidor no está incluido,
   porque es un servicio alojado que debe montar usted.

## Lo que queda fuera de este repositorio

- El servidor de sincronización alojada, el de la tienda de plugins y el
  reparto de ingresos con Stripe Connect (70/30). Son servicios en internet
  que hay que contratar y operar; el código local ya está preparado para
  ellos.
- Cobrar y facturar. Stripe se encarga de los impuestos y los recibos;
  revise las obligaciones fiscales de su país antes de vender.
