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
`checkout.session.completed`, `invoice.paid` y
`customer.subscription.deleted`.

**PayPal**: cobra un mes por cada pago.

```
PAYPAL_CLIENT_ID=...
PAYPAL_SECRET=...
PAYPAL_WEBHOOK_ID=...
PAYPAL_MODO=sandbox   # bórrelo para cobrar de verdad
```

En el panel de desarrollador de PayPal, cree un webhook con la dirección
`https://<su-dirección>/v1/pagos/aviso/paypal` y el evento
`PAYMENT.CAPTURE.COMPLETED`.

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
