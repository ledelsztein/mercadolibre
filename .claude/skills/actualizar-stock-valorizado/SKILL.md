---
name: actualizar-stock-valorizado
description: "Actualiza la pestaña 'stock_valorizado' del Google Sheet de Deleite (MercadoLibre) -- una foto diaria del stock de cada publicación activa (sin kits/combos) con precio publicado e importe (stock x precio). Usar SIEMPRE que Lucas pida el stock valorizado, cuánto vale el stock, o quiera guardar una foto del stock de hoy -- incluso si no menciona el nombre exacto de la pestaña."
---

# Actualizar stock_valorizado (Deleite / MercadoLibre)

Repo: `C:\Users\User\Projects\mercadolibre`. Todos los comandos se corren parados ahí.

Tabla nueva (2026-08-03, pedido de Lucas): a diferencia de todas las demás `base_*`, esta **no viene de Facturación ni de órdenes** -- es una foto del estado actual de las publicaciones (`/users/{seller_id}/items/search` + `/items`), pensada para ir armando un histórico día a día. Antes de esta tabla, "¿cuánto valía el stock ayer?" no se podía responder -- el pipeline solo trackeaba ventas, nunca inventario.

## Paso único -- recalcular y subir

```bash
python compute_stock_valorizado.py
python build_stock_valorizado_sheet.py
```

`compute_stock_valorizado.py` usa la fecha real del sistema por default (`date.today()`) -- **correr `date +%Y-%m-%d` antes si hay alguna duda** sobre qué día es hoy (ver la nota general del pipeline sobre esto). Si hace falta forzar una fecha puntual, se puede pasar como argumento: `python compute_stock_valorizado.py 2026-08-03`.

## Reglas de metodología -- no re-derivar

- **Excluye kits/combos**: cualquier publicación con el tag `"bundle"` en su lista de `tags` se saca -- son combos armados a partir de otros productos individuales que ya están en la tabla por separado, y no tienen stock propio real (confirmado con Lucas revisando un caso puntual, 2026-08-03: un ítem con ese tag resultó ser exactamente eso). **Solo publicaciones `status: active`** -- las pausadas/en revisión no suman valor real disponible para vender.
- **Importe = stock (`available_quantity`) × precio publicado (`price`)** -- precio de lista tal cual está publicado, no el precio de venta real de ninguna orden puntual (puede haber promociones que no se reflejen acá).
- **Una fila por publicación por día** -- correr esto más de una vez el mismo día **reemplaza** la foto de ese día (no duplica), pero nunca toca fotos de días anteriores. Así se va armando el histórico con el tiempo.
- **`SKU` puede venir vacío** para publicaciones sin `seller_sku`/`SELLER_SKU` cargado -- no es un error, dejarlo así.

## Cuándo correr esto

Es liviano (dos llamados paginados a la API, sin loop por orden) -- se puede correr todos los días como parte de `/actualizar-tablero` sin problema. Si Lucas pregunta "¿cuánto valía el stock de tal día?" y esa fecha no está en `stock_valorizado.json`, avisarle que no hay foto guardada de ese día (no se puede reconstruir con certeza hacia atrás, solo hacia adelante desde que se armó esta tabla el 2026-08-03).

Ver memoria `mercadolibre-pnl-pipeline` (sección "stock_valorizado") para más contexto.
