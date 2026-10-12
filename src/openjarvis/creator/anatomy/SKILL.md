---
name: anatomy
nombre: Anatomía (láminas isométricas de máquinas)
claves: anatomía, anatomia, isométrico, isometrica, lámina técnica, ilustración técnica, figura explicativa, explica cómo funciona, despiece, explosionado, máquina, mecanismo, diagrama bonito, infografía técnica, svg
origen: https://github.com/IvoSegovia/anatomy (MIT, © 2026 Ryan) — convertida para Sergio
---

# Anatomía, en Sergio

Sergio dibuja una idea técnica como **una máquina real, en isométrico**: una
lámina SVG interactiva (a veces con sombreadores WebGL) donde cada pieza es
un sólido pequeño y preciso, con sombreado de cuatro tonos, orden de pintado
correcto, una tarjeta con título, pista y lectura en vivo, y movimiento
suave. El lector entiende la idea porque reconoce la máquina.

Se usa desde **Creator → Anatomía** (galería de ejemplos y «Crear lámina») o
pidiéndoselo a Sergio («hazme una lámina isométrica que explique cómo
funciona una caché»). El kit vive en `creator/anatomy/kit/`; los ejemplos en
`creator/anatomy/examples/`; las guías completas en `references/` (en
inglés, del proyecto original). La herramienta es `anatomy_figure`.

## La idea que importa

**El objeto es la explicación.** Nada de cajas con flechas: se inventa una
máquina real cuyo funcionamiento *es* el concepto (una caché → una cerradura
de pines; un desenfoque separable → una cama de clavos frente a dos peines).
Dos fallos típicos: demasiado abstracto (placas flotando) o demasiado plano
(una losa con dos líneas). La cura es la misma: una máquina reconocible,
hecha de muchas piezas pequeñas con propósito.

## Tamaños (dígalo antes de empezar)

- **Figura**: un mecanismo, 40–80 piezas, SVG con a lo sumo una capa WebGL.
  30–90 min para una persona; Sergio la intenta directamente.
- **Héroe**: objeto denso, 80–150 piezas. Horas. Sergio avisa y propone.
- **Épica**: un vehículo, un edificio. No se empieza sin que el señor lo pida;
  se propone un Héroe con el núcleo de la idea.

## Flujo de trabajo (en este orden)

1. **Verdad primero**: cifras y comportamiento reales; lectura, movimiento y
   pie de figura deben ser ciertos (un modelo puro, como `rig.ts`).
2. **Inventar el objeto** y decir en una frase qué se mueve y qué significa.
3. **Lista de piezas** (≥ 40): base, estructura, mecanismo, mandos y el sujeto
   (la única pieza iluminada).
4. **Plan del mundo**: unidades ≈ 1 px, x/y en el suelo, z arriba; cámara a
   45° (35–60°), elevación 30°; `fitProjection(points, w, h, { pad, azimuth })`.
5. **Geometría una sola vez** con el kit: `slabOf`, `cylinder`, `extrude`,
   `planOutline`, `topTicks`, `knurl`, `coil`, `radialTicks`; redondos con
   `kit/lathe.mjs`; tubos y cables con `kit/tube.mjs`.
6. **Pintar de atrás adelante y de abajo arriba**; con tubos y piezas
   redondas, `A.recorder` + `A.settle` + `A.auditOrExit` (el orden se prueba,
   no se ajusta a ojo).
7. **Enmarcar**: «Fig n» arriba a la izquierda, título a la derecha, pista
   abajo a la izquierda, lectura en vivo abajo a la derecha.
8. **Darle vida**: movimiento por tiempo (resortes, seguimiento
   exponencial), recorrido en reposo, respeta «reducir movimiento».
9. **Verificar como un crítico**: auditoría a cero (`node build.mjs --audit`),
   líneas que terminan en algo, capturas a 4× en tema claro y oscuro.

## Reglas de oficio (resumen)

- Sólidos, nunca alambres; el kit sombrea (`extrude` da cuatro tonos).
- Jerarquía de tonos: base `lo`, estructura `mid`, sujeto `hi`, un solo `lit`.
- Detalle pequeño y preciso con propósito (biseles 0,4–1,6; tornillos como
  puntos; reglas con marcas cada 4–5 unidades).
- Toda línea termina en algo; ningún tubo atraviesa nada; los cruces en orden
  de profundidad real; las superficies curvas sombrean sin escalones.
- Volumen y composición: la figura llena ~55–65 % de la tarjeta y se lee a
  390 px de ancho.

## Cómo lo hace Sergio (herramienta `anatomy_figure`)

- `examples`: lista las láminas de ejemplo (indicador de cuadrante,
  ordenador de escritorio, máquina recreativa, cubeta de ondas, motor
  cohete, cuadrante giratorio).
- `build`: construye un ejemplo (Node.js) y devuelve la página HTML.
- `create`: Sergio escribe el `build.mjs` de una lámina nueva con el kit, la
  construye y, si Node da un error, lo corrige y lo intenta otra vez (hasta
  3 veces). Nunca dice que está hecha si Node no la construyó.

Créditos: el kit, las guías y los ejemplos son de *anatomy* (MIT), adaptados
para Sergio. La licencia original está en `LICENSE`.
