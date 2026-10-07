---
nombre: Color y entrega de video
claves: color, colorimetria, etalonaje, gradea, grading, davinci, resolve, log, slog, s-log, rec.709, rec709, hdr, lut, video
---
- Flujo gestionado: CST de entrada (perfil Log de la cámara a DaVinci Wide Gamut / Intermediate), corrección en ese espacio, CST de salida al destino. Nunca corregir Log directamente en Rec.709.
- Balance neutro: nodo en espacio Linear y ajuste con Gain. Primarias con Lift, Gamma, Gain y Offset.
- Contraste en DaVinci Intermediate con pivote 0.336 para proteger los medios tonos.
- Secundarias con calificadores HSL/3D (suavizar con Blur Radius, Clean Black/White) en nodos de mezcla paralela (Parallel Mixer), no en serie.
- Piel: las muestras caen sobre la línea de piel del vectorscopio.
- Entrega: TV Rec.709 gamma 2.4 (ProRes 422 HQ o DNxHR HQX); web y Mac Rec.709-A / gamma 2.2 en H.264/H.265 (evita el cambio de gamma de QuickTime); cine DCI-P3 gamma 2.6; HDR Rec.2020 PQ o HLG. Siempre indicar el gamma de salida.
- Multiformato: gradear primero en el espacio más amplio (HDR) y derivar las versiones cambiando solo el CST de salida.
