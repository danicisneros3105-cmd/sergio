# Lanzamiento: lo que falta para publicar Sergio

Se comprueba solo con `sergio lanzamiento` (o `GET /v1/pagos/lanzamiento`).
El comando separa dos listas:

- **Del código**: Sergio mira su propia configuración y dice qué está listo.
- **Del dueño**: pasos que solo una persona puede dar. **Nunca se marcan solos**;
  el comando siempre los muestra como pendientes.

## Pasos del código (se arreglan con configuración)

| Paso | Cómo se arregla |
|---|---|
| Edición pública | `SERGIO_EDICION=publica` en el servidor de clientes (`docs/LEGAL-TERCEROS.md`) |
| Registro abierto con verificación | `SERGIO_REGISTRO=abierto` y el correo SMTP que envía los códigos |
| Dirección pública con https | `SERGIO_PUBLIC_URL=https://…` |
| Claves de IA por cliente | Clave de gestión de OpenRouter en `~/.openjarvis/sergio.env` |
| Cifrado de datos sensibles | Ya viene activo (`SERGIO_CIFRAR=0` lo apaga: no usarlo) |
| Clave maestra fuera del disco | `sergio boveda proteger` (llavero con frase) o `SERGIO_CLAVE_MAESTRA` desde un gestor de secretos |
| Cobros | Stripe o PayPal con sus claves en `sergio.env` |

Las claves viven solo en `sergio.env`, nunca en el repositorio.

## Pasos del dueño (nadie más los puede dar)

1. **Empresa internacional y cuenta bancaria.** Elija jurisdicción con un
   contador. Sin empresa no se abre Stripe/PayPal ni se firman contratos.
2. **Términos de uso y privacidad revisados por un abogado.** Los borradores
   del repositorio son criterio, no texto legal. Sergio ya guarda la versión
   aceptada, la mayoría de edad y la fecha de cada registro.
3. **Nombre y marca.** Búsqueda de disponibilidad y registro de «Sergio» y del
   nombre provisional «Visage» (la marca «Face ID» es de Apple).
4. **Certificado de firma de código** para el instalador de Windows; sin él
   Windows avisa «aplicación no reconocida».
5. **Repositorio privado.** Hoy es público: cualquiera puede copiar el código.
6. **Cifrado del disco y copias cifradas** en el servidor. El cifrado por campo
   no cubre archivos de proyectos ni registros.
7. **Auditoría externa de seguridad.** Hasta tenerla no se dice «nivel
   bancario»; se dice AES-256-GCM, que es lo que es.
8. **Beta cerrada** con personas y facturas reales para confirmar costos
   (`docs/ECONOMIA.md`).
9. **Términos de OpenRouter y de cada proveedor de IA**, leídos por escrito,
   para confirmar que se puede revender el acceso.

## Lo que seguirá sin hacerse

- Desbloquear Windows, macOS o el teléfono: ningún sistema se lo permite a una
  app (`docs/FACEID-SISTEMA.md`).
- Probar de punta a punta pagos, llamadas, publicación y cámara con servicios
  reales: es trabajo de la beta.
