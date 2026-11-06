# Sergio Pagos

La caja de cobro propia de Sergio: página de pago con el diseño de Sergio,
pedidos, libro de cuentas y activación automática del plan. Debajo hay un
procesador con licencia que mueve el dinero. Sergio no puede ser ese
procesador por sí solo: para eso hace falta un banco adquirente, la norma
PCI DSS y licencias de transmisor de dinero.

## Cómo fluye el dinero

1. El cliente elige un plan en **Planes** y pasa a **Pagar** (`/pagar`).
2. Escribe su tarjeta en la página segura del procesador. Sergio nunca ve la
   tarjeta.
3. El procesador avisa a Sergio con un aviso firmado
   (`/v1/pagos/aviso/<metodo>`). Sergio comprueba la firma y el importe, y
   anota el ingreso, la comisión, el tope de IA y la ganancia.
4. Sergio activa el plan solo: crea o ajusta la subclave de OpenRouter del
   cliente con el tope = precio − margen (`accounts/provision.py`).
5. El procesador deposita el dinero en la cuenta bancaria del dueño, en los
   días que fija el procesador.
6. OpenRouter cobra la IA con la recarga automática desde la tarjeta del
   dueño. «Cobros», en Planes → Facturación, avisa si el saldo no cubre lo
   que los clientes pueden gastar.
7. Si un mes pagado termina sin renovarse, el cliente vuelve a Free solo
   (revisión cada hora).

## Qué va dónde

| Dato | Dónde |
|---|---|
| Cuenta bancaria, RUC, identidad | Solo en el panel del procesador (Stripe, PayPal o la pasarela local). Nunca en Sergio, nunca en un chat. |
| Claves de API y secretos de avisos | Solo en `~/.openjarvis/sergio.env` |
| Tarjetas de los clientes | Solo en el procesador |

## Formas de pago (actívelas con sus claves en `sergio.env`)

**Tarjeta (Stripe)**: se renueva sola cada mes.

```
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

En el panel de Stripe, en Webhooks, cree un destino con la dirección
`https://<su-dirección>/v1/pagos/aviso/stripe` y estos eventos:
`checkout.session.completed`, `checkout.session.async_payment_succeeded`,
`checkout.session.async_payment_failed`, `checkout.session.expired`,
`invoice.paid` y `customer.subscription.deleted`. Habilite el portal de
clientes en el panel de Stripe para que el cliente pueda gestionar su
suscripción. Configure métodos dinámicos en ese panel: Stripe enseña los
medios compatibles con la moneda, el país, el dispositivo y la suscripción.

**PayPal**: cobra un mes por cada pago.

```
PAYPAL_CLIENT_ID=...
PAYPAL_SECRET=...
PAYPAL_WEBHOOK_ID=...
PAYPAL_MODO=sandbox   # bórrelo para cobrar de verdad
```

En el panel de desarrollador de PayPal, cree un webhook con la dirección
`https://<su-dirección>/v1/pagos/aviso/paypal` y estos eventos:
`PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.DENIED`,
`PAYMENT.CAPTURE.REFUNDED`, `PAYMENT.CAPTURE.REVERSED` y
`CHECKOUT.PAYMENT-APPROVAL.REVERSED`.

**Tarjeta y pagos locales (Hyperswitch, código abierto Apache-2.0, alojado por
usted)**: un orquestador propio que conecta con pasarelas de su país.

```
HYPERSWITCH_URL=https://<su-hyperswitch>
HYPERSWITCH_API_KEY=...
HYPERSWITCH_HASH_KEY=...   # payment_response_hash_key del perfil
```

Su aviso va a `https://<su-dirección>/v1/pagos/aviso/hyperswitch`.

**Para todas**: `SERGIO_PUBLIC_URL=https://<su-dirección>` (la dirección
pública, por ejemplo el túnel) y `OPENROUTER_MANAGEMENT_KEY` para las
subclaves. `SERGIO_COMISION_STRIPE=0.029+0.30` corrige la comisión estimada
del libro. `SERGIO_MARGEN` (0.40) es su ganancia sobre cada plan.

## Seguridad

- **Claves de IA de los clientes cifradas** con AES-256-GCM, atadas a cada
  cliente: una clave copiada a otro cliente no abre. La clave maestra está en
  `~/.openjarvis/clave_maestra` (0600) o en `SERGIO_CLAVE_MAESTRA`. Guarde
  una copia fuera del PC; nunca la suba ni la comparta.
- **Libro sellado**: cada línea lleva un HMAC de su contenido y de la línea
  anterior. Si alguien edita, borra o mete una línea a mano, «Cobros» dice
  «Alterado en la línea N». Una devolución es una línea nueva en negativo,
  nunca un borrado.
- **Avisos**: firma comprobada (Stripe y Hyperswitch con HMAC; PayPal lo
  verifica con PayPal), avisos de más de 5 minutos rechazados, tope de
  256 KB, cada evento cuenta una sola vez, importe y moneda (USD)
  comprobados.
- **Pagos repetidos**: cada pedido va con su clave de idempotencia
  (`Idempotency-Key` en Stripe, `PayPal-Request-Id` en PayPal). Un doble
  clic no cobra dos veces.
- **Dinero real solo con https**: con claves reales (`sk_live_`), Sergio no
  abre un cobro si `SERGIO_PUBLIC_URL` no empieza con `https://`.
- **Freno**: como mucho 5 intentos de pago por cuenta cada 10 minutos.
- **Devoluciones y contracargos**: los de PayPal llegan solos. Los de Stripe
  se hacen en su panel y se marcan con «Devolver» en Cobros. En los dos casos
  el plan del cliente termina y su clave de IA vuelve a Free.

## Comprobar con su propia tarjeta ($1)

Cuando ya tenga claves reales, en Planes → Facturación → Cobros pulse
**«Probar con mi tarjeta ($1)»**:

1. Se abre la página segura de Stripe o PayPal. Escriba ahí su tarjeta, y
   solo ahí: nunca en Sergio ni en un chat.
2. Al pagar, verá «Listo» con su número de recibo (`SG-AAAA-000001`).
3. En Cobros aparece el dólar, la comisión y el libro intacto.
4. Devuelva el dólar desde el panel del procesador y pulse «Devolver» en
   el pedido.

Así comprueba el camino entero con dinero real sin dar su tarjeta a nadie.
«Revisar claves con los procesadores» le pregunta a Stripe o PayPal si sus
claves funcionan.

## Cómo probarlo sin su tarjeta (recomendado antes de cobrar)

Su tarjeta real no hace falta para probar, y nunca debe escribirse en un chat.
Los procesadores tienen un modo de prueba con tarjetas falsas públicas:

1. En Stripe, use el **modo de prueba** y ponga las claves `sk_test_...` y
   `whsec_...` en `sergio.env`.
2. Entre a Sergio con una cuenta de cliente aprobada, elija un plan y pague
   con la tarjeta de prueba de Stripe **4242 4242 4242 4242**, cualquier fecha
   futura y cualquier CVC.
3. En segundos, la página dice «Listo», el plan queda activo y «Cobros» lo
   anota. No se mueve dinero real.
4. Para PayPal, ponga `PAYPAL_MODO=sandbox` y pague con una cuenta de prueba
   del panel de desarrollador de PayPal.

Cuando todo salga bien, cambie a las claves `sk_live_...` y quite
`PAYPAL_MODO`.

## Límites honestos

- Las comisiones del libro son estimadas. La cifra exacta está en el panel
  del procesador.
- Payphone y Kushki (Ecuador) se conectan por Hyperswitch. No se
  integraron directo porque no se pudo verificar su API pública.
- Las pruebas usan respuestas simuladas de los procesadores. El primer cobro
  real conviene hacerlo en modo de prueba (claves `sk_test_`,
  `PAYPAL_MODO=sandbox`).

## Cuenta bancaria, saldo de IA y referidos

1. Registre la cuenta bancaria del negocio en el portal del procesador;
   el retiro a débito solo existe para cuentas y tarjetas elegibles. Use la
   jurisdicción real de su negocio y un representante autorizado. No ponga
   números de tarjeta en Sergio, GitHub, ni en su archivo de configuración.
2. En [OpenRouter → Saldo](https://openrouter.ai/settings/credits) el titular
   registra su medio de pago y, si lo elige, habilita la recarga automática.
   Es un cargo separado del depósito de la pasarela: reserve caja suficiente.
   Configure una clave de gestión de OpenRouter en el servidor para que Sergio
   active y limite las claves de sus clientes; los clientes no copian claves.
   Para cuentas privadas de Higgsfield u otros servicios sigue siendo necesaria
   una autorización personal mediante el proveedor.
3. Compare comisiones y consumos reales con `/v1/pagos/economia`, incluido el
   costo de infraestructura y de recarga. El margen del libro no es ganancia
   contable ni incluye impuestos o contracargos.

Referidos es un piloto **apagado por defecto** (`SERGIO_REFERIDOS=1` y Stripe
o PayPal en vivo). No habilite el piloto hasta configurar los avisos y el portal, y
verificar el recorrido en una cuenta de prueba. Un cliente activo comparte
su código desde Perfil; el invitado lo ingresa antes de abrir su primer
checkout. Solo el primer plan pagado y elegible de una cuenta, confirmado por
una pasarela en vivo, otorga dos descuentos. Nunca cuentan los cobros de prueba
ni un pago no confirmado. Hay 30 días de espera.

El descuento se aplica al siguiente pago elegible en PayPal o a la primera
factura de una **nueva** suscripción en Stripe. No se acumula ni modifica
suscripciones vigentes o renovaciones de Stripe. Es de hasta
5% del nuevo plan y nunca mayor al 5% del primer pago que generó el descuento.
El cálculo reserva el costo total de IA, recarga, comisiones e infraestructura,
y exige al menos 15% de margen de contribución o $1, el mayor. Con los
supuestos del repositorio, Go queda fuera; Work, Dev y Founders califican.
Eso no garantiza ganancias con tarifas o costos distintos. Compruebe que
la comisión, gastos y reserva real correspondan a sus valores.

Registre inmediatamente en Cobros los reembolsos y contracargos de Stripe
que se gestionen en su panel: no se reconcilian automáticamente todos los
reembolsos de suscripción de Stripe. Un reembolso registrado antes de usar
el cupón invalida el saldo disponible para ambos. Si una sesión no se pudo
abrir y no llega un aviso de cierre de la pasarela, revise el intento antes de abrir
otro con descuento. Mantenga el piloto apagado si no puede conciliarlo.
