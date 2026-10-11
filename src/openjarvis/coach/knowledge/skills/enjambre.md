---
nombre: Enjambre de agentes
claves: compara, investiga, analiza, varios, cada uno, todos los, lista de, en paralelo, a la vez, informe, tabla
---
- Divide el trabajo en un grafo: pasos independientes a la vez, y los que dependen de otros después.
- Lo repetido por elemento (cada producto, cada ciudad, cada archivo) es un solo paso con su lista: un subagente por elemento, ejecutados por un pool limitado (8 por defecto), nunca un hilo por elemento.
- Cada subagente devuelve solo su conclusión verificada, corta, con fuente; nada de volcados largos.
- Antes de entregar, un revisor que no hizo el trabajo comprueba punto por punto contra lo pedido.
