---
name: browser-shopping
description: Automatización de compras online, delivery (Uber Eats, Rappi, PedidosYa) y comercio multicanal (Amazon, Mercado Libre, eBay, Marketplace).
license: Apache-2.0
metadata:
  openjarvis:
    user_invocable: false
---

# Browser Shopping & Multi-Platform Commerce

Automatización integral de navegación web y aplicaciones de comercio electrónico y delivery.

**Regla del dueño:** todo se hace solo hasta el último clic; pagar, confirmar el pedido, publicar o enviar un mensaje espera su sí a exactamente eso (`confirmed=true` solo después). Las contraseñas las escribe él en pantalla.

## 1. Delivery Inmediato (Uber Eats, Rappi, PedidosYa)
- Búsqueda de restaurantes abiertos en rango local.
- Optimización de presupuesto: cálculo de subtotal + envío + tarifas de servicio para ajustarse al límite estricto del usuario.
- Llenado autónomo de formularios de dirección y selección de método de pago predeterminado.

## 2. Compras en E-commerce (Amazon, Mercado Libre, eBay)
- Comparación de precios y reputación de vendedores (filtrar vendedores con calificación >= 98% y envíos garantizados).
- Incorporación directa a carrito y seguimiento de pedidos.

## 3. Venta Cruzada (Marketplace, Wallapop, eBay)
- Inspección de fotografías del producto en el dispositivo.
- Redacción de títulos persuasivos con palabras clave SEO y fichas técnicas completas.
- Anuncios y respuestas a compradores listos para que él los apruebe antes de publicar o enviar.
