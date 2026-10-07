---
nombre: Blender de producción
claves: blender, 3d, modelo, modela, render, renderiza, escena, vfx, cycles, eevee, unreal, ue5, usd, alembic
---
- Escala real 1:1 en metros; para Unreal Engine 5 se exporta en centímetros.
- Antes de entregar: normales hacia fuera, sin geometría non-manifold ni vértices sueltos, shade smooth (o weighted normals) en lo curvo.
- Piezas repetidas como duplicados enlazados (comparten la malla: 0 memoria extra); cientos de copias con instancias de Geometry Nodes.
- Render final Cycles: 256–512 muestras, umbral de ruido 0.01 con mínimo 32, OIDN u OptiX con pases de albedo y normales, rebotes totales 8–12, difusos 4–8, transparencia 16–32, volumen 0 salvo humo o fuego.
- Eevee Next: 64 muestras TAA y trazado de rayos en pantalla.
- Memoria: Persistent Data activado; simulaciones (tela, partículas, fluidos, cuerpos rígidos) horneadas a disco antes del render.
- Composición: OpenEXR multicapa de 32 bits con pases Z (Defocus), vector (Vector Blur), Cryptomatte y difuso/especular separados.
- Intercambio: OpenUSD para escenas con cámaras, luces e instancias; Alembic para geometría deformada (tela, pelo); animación de vértices a texturas (VAT) para motores en tiempo real.
