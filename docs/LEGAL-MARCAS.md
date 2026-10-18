# Logos de universidades y marcas de terceros

Resumen para el dueño (octubre de 2026). **No es asesoría legal**: es lo que
dicen las normas públicas de cada universidad y la regla general del uso
nominativo. Ante una duda concreta, consulte a un abogado.

## Lo que decidimos

- En **Salud mental** y en el **gimnasio mental**, al final de cada apartado y
  en letra pequeña, Sergio nombra las investigaciones que usa (autores, revista,
  año, DOI) y **el nombre de la institución donde se hizo cada una, como texto**.
- Va siempre con este aviso: Sergio no tiene relación con esas instituciones ni
  cuenta con su aval.
- **Ningún logo de universidad viene con Sergio.** Si el dueño consigue permiso
  por escrito de una universidad, puede poner su logo en
  `~/.openjarvis/instituciones/<clave>.png` (o `.svg` / `.webp`, máximo 300 KB)
  y Sergio lo mostrará junto al nombre. Las claves están en
  `src/openjarvis/health/credits.py` (`columbia`, `indiana`, `pennstate`,
  `michigan`, `chicago`, `bern`, `uci`, `ubc`, `saarland`).

## Por qué

1. **Los logos son marcas registradas.** Las universidades protegen sus
   escudos, sellos y logotipos y exigen licencia o permiso para usarlos fuera de
   la institución, sobre todo en productos.
   - Universidad de Columbia: sus normas de identidad visual reservan el uso de
     sus marcas a la universidad y piden autorización para terceros.
   - Penn State: el uso por terceros pasa por su oficina de licencias
     (licensing.psu.edu, licensing@psu.edu).
   - Universidad de Míchigan: normas de marca en brand.umich.edu; permisos y
     licencias en licensing@umich.edu.
   - UCLA: marcas en marks.ucla.edu y la política 110 de la UC sobre el uso del
     nombre de la universidad; prohíbe insinuar aval sin autorización.
   - Universidad de Chicago: no encontramos una política pública concreta; se
     trata igual que las demás.
2. **Nombrar sí está permitido (uso nominativo).** Decir con palabras quién hizo
   un estudio, sin logos, sin destacarlo más de lo necesario y sin dar a
   entender patrocinio, es la forma aceptada de referirse a una marca ajena
   (doctrina del «uso nominativo», p. ej. *New Kids on the Block v. News
   America Publishing*, 9.º Circuito de EE. UU., 1992). Por eso los nombres van
   en texto y con el aviso de no afiliación.
3. **Un logo junto a un producto sugiere aval**, que es justo lo que las normas
   de esas universidades prohíben sin permiso.

## Cómo pedir permiso (si el dueño lo quiere)

Escribir a la oficina de marca o licencias de la universidad diciendo: qué es
Sergio, dónde se vería el logo (solo en los créditos de Salud mental o del
gimnasio, en pequeño), que no es para vender ni para sugerir aval, y pedir la
respuesta por escrito. Con ese permiso, colocar el archivo como se explica
arriba.

## Las demás marcas

La regla de la casa sigue igual (AGENTS.md): **todo es Sergio**. Los programas
de terceros que Sergio usa por dentro se ven con nombres de Sergio (por ejemplo,
el agente de código basado en OpenClacky se ve como «Agente de código»; el
parche está en `scripts/marca_agente.py`). Sus créditos y licencias se respetan
en NOTICE, en las licencias originales y en «Acerca de».
