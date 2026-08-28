---
name: monitorear-mayorista-enm
description: "Revisa la lista de precios del mayorista ENM (Google Drive, archivo 'Mayoristas ENM - ACTUALIZACION...') y avisa si cambió el precio de algún ítem o si algún ítem desapareció de la lista respecto del último chequeo. Usar SIEMPRE que se dispare el chequeo diario del mayorista ENM, o que Lucas pida 'revisá la lista del mayorista', 'chequeá precios de ENM', o algo equivalente."
---

# Monitorear lista de precios del mayorista ENM

Repo: este mismo repo (`mercadolibre`). Todos los comandos se corren parados en la raíz.

No es parte del pipeline de P&L de Deleite -- es un monitoreo aparte de un archivo de
un proveedor (Nogal Depósito / ENM), compartido a Lucas por Google Drive, para avisarle
si suben precios o discontinúan productos.

- `file_id` de Drive: `11Q9Pu6J0LFf_DFfbCk2DYSD3KFd66ZVz` (dueño `elnogaldeposito@gmail.com`).
- URL original: `https://docs.google.com/spreadsheets/d/11Q9Pu6J0LFf_DFfbCk2DYSD3KFd66ZVz/edit?gid=919713446#gid=919713446`
- Snapshot anterior versionado en `monitoring/mayoristas_enm/snapshot.txt` (+ `meta.json` con la fecha del último chequeo).

## Por qué el enfoque es "diff de texto" y no un parser de filas

El archivo es un `.xlsx` real (no un Google Sheet nativo) con ~15 pestañas de proveedores
distintos, cada una con su propio formato de columnas (a veces "Producto,Presentación,Precio",
a veces varias columnas de precio por cantidad, promos sueltas, emojis, etc.). La herramienta
`read_file_content` de Google Drive devuelve **todo el contenido aplanado en un solo bloque**,
sin separar pestañas ni filas con saltos de línea reales -- las filas quedan separadas por
corridas de comas (`,,,,,` o similar, variable según la pestaña).

Ya se probó parsear esto como tabla estructurada (producto/precio por columna) y no vale la
pena: no hay un esquema único, cambia de pestaña a pestaña. El enfoque que funciona es:
normalizar el bloque a texto línea por línea (partiendo por corridas de 2+ comas) y comparar
ese texto contra el snapshot del día anterior con `diff`. Alcanza para detectar qué segmento
cambió; el criterio de "¿es un cambio de precio, una baja de producto, o ruido cosmético?" lo
aplica el modelo leyendo el diff, no un regex.

## Pasos

1. **Traer el contenido actual** con la herramienta `mcp__Google_Drive__read_file_content`
   (`fileId: 11Q9Pu6J0LFf_DFfbCk2DYSD3KFd66ZVz`). El resultado es grande (~100k caracteres) y
   puede volcarse a un archivo de resultados de herramienta -- leerlo desde ahí si hace falta.

2. **Normalizar** el `fileContent` a un archivo de texto, una línea por registro, partiendo
   por corridas de 2 o más comas y descartando líneas vacías:

   ```bash
   python3 -c "
   import json, re, sys
   content = json.load(open(sys.argv[1]))['fileContent']
   parts = [p.strip() for p in re.split(r',,+', content) if p.strip()]
   open(sys.argv[2], 'w').write('\n'.join(parts) + '\n')
   " <archivo_resultado_de_la_tool> monitoring/mayoristas_enm/current.txt
   ```

3. **Diff contra el snapshot anterior**:

   ```bash
   diff monitoring/mayoristas_enm/snapshot.txt monitoring/mayoristas_enm/current.txt
   ```

   Si no hay diferencias, no hay nada para avisar -- ir directo al paso 6 (igual actualizar
   `meta.json` con la fecha del chequeo).

4. **Interpretar el diff** línea por línea (comparando `<` líneas viejas vs `>` líneas nuevas):
   - **Cambio de precio**: una línea `<` y una línea `>` que mencionan el mismo producto
     (mismo nombre / misma presentación) pero con un monto `$` distinto.
   - **Ítem desaparecido**: una línea `<` con un producto que no tiene ninguna línea `>`
     correspondiente en el nuevo contenido (buscar el nombre del producto en todo
     `current.txt`, no solo en el diff, por si se movió de posición).
   - **Ítem nuevo**: una línea `>` sin correspondencia en `snapshot.txt` -- no es lo que Lucas
     pidió que se le avise activamente, pero si aparece se puede mencionar de paso, no hace
     falta profundizar.
   - Ignorar diferencias puramente cosméticas: encoding de emojis, mayúsculas/minúsculas,
     espacios, reordenamiento de pestañas sin cambio de contenido real.

5. **Actualizar el snapshot y el registro**:
   ```bash
   mv monitoring/mayoristas_enm/current.txt monitoring/mayoristas_enm/snapshot.txt
   ```
   Actualizar `monitoring/mayoristas_enm/meta.json`: `last_checked` (fecha real de hoy,
   correr `date +%Y-%m-%d`, nunca asumir) y `last_seen_modified_time` (con
   `mcp__Google_Drive__get_file_metadata` sobre el mismo `file_id`).

6. **Commitear y pushear a `main`** (no es un cambio de código, es una actualización de datos
   como las `base_*.json` -- va directo, sin PR):
   ```bash
   git add monitoring/mayoristas_enm/
   git commit -m "Monitor mayorista ENM: chequeo <fecha> -- <resumen corto de lo encontrado o 'sin cambios'>"
   git push origin main
   ```

7. **Reportar a Lucas** en un mensaje final claro: si hubo cambios de precio o ítems
   desaparecidos, listarlos explícitamente (producto, precio viejo -> precio nuevo, o
   "ya no aparece en la lista"). Si no hubo cambios, decirlo en una sola línea -- no hace
   falta detalle. Este mensaje es el que dispara la notificación push/email de la corrida.
