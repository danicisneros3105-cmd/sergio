# Ganancias y costos de Sergio

2 de noviembre de 2026. Cálculo hecho por `src/openjarvis/pagos/economia.py`
(`GET /v1/pagos/economia`, solo el dueño; `tests/pagos/test_economia.py`).

> **Todas las tasas son supuestos que hay que confirmar** con las listas de
> precios vigentes y con las primeras facturas reales. Están en variables de
> entorno para corregirlas sin tocar código. Esto no es una promesa de
> ganancia: es la forma de saber si un plan pierde dinero antes de venderlo.

## Cómo se calcula (por cliente y por mes)

```
precio
− lo que se queda el procesador de pagos   (2,9 % + 0,30 $; +1,5 % si la tarjeta es de otro país; +1 % si hay cambio de moneda)
− la IA que usa (nunca más que el tope de su clave)
− lo que se queda OpenRouter al comprar créditos (5,5 %)
− hosting y soporte por cliente (0,40 $)
= lo que le queda al dueño
```

Supuestos que están puestos y no medidos: 70 % de clientes con tarjeta de
otro país, un cliente típico gasta el 35 % de su tope de IA, un usuario Free
gasta el 30 % del suyo, y el hosting cuesta 0,40 $ por cliente de pago y
0,05 $ por usuario Free.

## Resultado con esos supuestos

| Plan | Precio | Comisión | Tope de IA | Peor caso (gasta todo el tope) | Típico (35 % del tope) |
|---|---|---|---|---|---|
| Go | $5 | $0,53 | $2,50 | **$1,43 (29 %)** | $3,15 (63 %) |
| Work | $21 | $1,28 | $12,60 | $6,03 (29 %) | $14,67 (70 %) |
| Dev | $50 | $2,62 | $30,00 | $15,33 (31 %) | $35,90 (72 %) |
| Dev (máx.) | $115 | $5,65 | $69,00 | $36,15 (31 %) | $83,47 (73 %) |
| Founders | $99 | $4,90 | $59,40 | $31,03 (31 %) | $71,77 (73 %) |
| Founders (máx.) | $235 | $11,23 | $141,00 | $74,62 (32 %) | $171,31 (73 %) |

**Free**: cada usuario cuesta entre $0,21 (típico) y $0,58 (peor caso). Con
estos números, **un cliente Go típico paga por unos 15 usuarios Free**.

## Lo que dice este cálculo

1. **Ningún plan pierde dinero aunque el cliente use todo su tope**, porque la
   clave de IA tiene un tope mensual que corta a OpenRouter. El margen general
   (`SERGIO_MARGEN`, 0,40) deja el 60 % del precio para IA; Go reserva 50 %
   (`SERGIO_MARGEN_GO`) y deja un tope de $2,50.
2. **Go sigue siendo el plan más frágil**: en el peor caso deja $1,43. Un
   reembolso o contracargo puede superar esa cantidad. Por eso su tope ya usa
   un margen propio del 50 %; hay que revisarlo con facturas reales.
3. **Free es el costo de adquirir clientes**, no un regalo gratis: si de cada
   100 usuarios Free menos de 7 pasan a Go, el Free pierde dinero. Hay que
   medir esa conversión en la beta.
4. **El número que más pesa es el uso típico** (35 %), y es una suposición. Con
   la beta se mide con el panel de ganancia por cliente (Planes → Cuenta) y se
   corrige `SERGIO_USO_TIPICO`.

## Lo que falta para tener números reales

- Facturas reales de Stripe/PayPal y de OpenRouter (comisión efectiva).
- Costo real de la nube (servidor, base de datos, copias de seguridad, correo
  y SMS de verificación: los SMS cuestan por mensaje y no están en el cálculo).
- Impuestos: IVA o *sales tax* según el país del cliente (Stripe Tax los
  calcula); el precio mostrado puede llevarlos dentro o encima, y eso cambia la
  columna «Precio».
- Devoluciones y contracargos (un porcentaje de las ventas).
- Costos de producto fijos: dominio, correo, firma de código del instalador,
  abogado, contador, auditoría de seguridad.

## Cómo se define el negocio

- **Ingreso**: planes mensuales en dólares, cobrados por un procesador con
  licencia (nunca por Sergio mismo).
- **Costo variable**: IA (acotado por el tope de cada clave), comisión de pago.
- **Costo fijo**: nube, firma, legales, soporte.
- **Punto de equilibrio**: costos fijos del mes ÷ ganancia típica por cliente.
  Con $3,15 en Go y $14,67 en Work, cubrir por ejemplo $1.000 al mes de costos
  fijos pide unos 69 clientes Work, o unos 318 Go. Son cuentas de ejemplo con
  supuestos, no una previsión.
