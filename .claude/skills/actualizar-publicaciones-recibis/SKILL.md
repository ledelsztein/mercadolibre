---
name: actualizar-publicaciones-recibis
description: "Actualiza la pestaña 'publicaciones_recibis' del Google Sheet de Deleite (MercadoLibre) -- una foto diaria de cuánto recibe Lucas neto por cada publicación activa si se vende a precio de lista hoy (Precio - Comisión - Envío absorbido). Usar SIEMPRE que Lucas pida el 'Recibís' de una publicación, cuánto recibe neto por un producto, o quiera saber el margen real después de comisión y envío -- incluso si no menciona el nombre exacto de la pestaña."
---

# Actualizar publicaciones_recibis (Deleite / MercadoLibre)

Repo: raíz del checkout de `ledelsztein/mercadolibre`. Todos los comandos se corren parados ahí.

Tabla nueva (2026-09-15, pedido de Lucas): a diferencia de `stock_valorizado` (que valoriza a
precio de lista sin descontar nada), esta tabla calcula el **importe neto real** que Lucas
recibiría por cada publicación si se vendiera hoy -- descontando la comisión de MercadoLibre
y, cuando aplica, el costo de envío que el vendedor absorbe por ofrecer envío gratis.

## Paso único -- recalcular y subir

```bash
python compute_publicaciones_recibis.py
python build_publicaciones_recibis_sheet.py
```

`compute_publicaciones_recibis.py` usa la fecha real del sistema por default
(`date.today()`) -- **correr `date +%Y-%m-%d` antes si hay alguna duda** sobre qué día es
hoy. Para forzar una fecha puntual: `python compute_publicaciones_recibis.py 2026-09-15`.

Es más pesado que `stock_valorizado`: hace 1-2 llamados extra por publicación (no se puede
batchear como `/items`). Con ~47 publicaciones activas tarda unos segundos, nada grave, pero
si el catálogo crece mucho puede valer la pena revisar el throttling (ya tiene un `sleep(1)`
cada 10 publicaciones).

## Metodología -- validada a mano contra el panel real de MercadoLibre, no re-derivar

Confirmado comparando contra 3 capturas reales del ícono "i" junto a "Recibís" en el panel
de publicaciones de Lucas (2026-09-15): Treonato De Magnesio ($15.174), Creatina ENA Sport
($20.510), Cuchillo Asado Nicols Delta ($29.067,56, con promoción activa incluida).

1. **Comisión**: `GET /sites/MLA/listing_prices` con `category_id`, `price`,
   `listing_type_id`, `logistic_type`, `shipping_mode`, `billable_weight` -- estos 4 últimos
   son **obligatorios en Argentina**; sin ellos el `fixed_fee` que devuelve no coincide con
   lo que MercadoLibre cobra en la realidad. Si la publicación tiene una campaña de cuotas
   activa (`sale_terms.INSTALLMENTS_CAMPAIGN`), pasarla como `tags` -- si no se manda, el
   costo de financiación queda subestimado. `sale_fee_amount` de la respuesta ya es el costo
   total por vender (cargo por vender + costo fijo por unidad + costo de cuotas, todo sumado)
   -- **no sumarle nada más encima**.
2. **Envío absorbido**: solo aplica si `shipping.free_shipping` del ítem es `true` (envío
   gratis a cargo del vendedor). En ese caso: `GET /users/{seller_id}/shipping_options/free`
   con `dimensions` (formato `"LxWxH,peso_gramos"`, de los atributos `SELLER_PACKAGE_LENGTH`
   / `_WIDTH` / `_HEIGHT` / `_WEIGHT`, o los `PACKAGE_*` de ML si el vendedor no cargó los
   propios), `item_price`, `listing_type_id`, `mode` (`shipping.mode` del ítem), `condition`,
   `logistic_type`, `free_shipping=true`. El campo `coverage.all_country.list_cost` es el
   envío que absorbe Lucas. Si `free_shipping` es `false`, el comprador paga el envío y esto
   queda en 0 -- **no llamar a este endpoint en ese caso** (ahorra llamadas).
3. **Recibís = Precio - Comisión - Envío absorbido** (por unidad). **Recibís Total = Recibís × Stock disponible** -- es el que hay que usar para "si vendo todo el stock, cuánto entra" (tabla `balance_salida`, no confundir con el Recibís por unidad).

No usar `/items/{id}/shipping_options` (sin `/free`) para esto -- ese es para cotizar el
envío que paga el comprador según destino, no el que absorbe el vendedor; da un número
distinto (confirmado con un caso real: $4.491 contra el $7.790 real).

## Reglas de metodología -- no re-derivar

- **Excluye kits/combos**: mismo criterio que `stock_valorizado` -- cualquier publicación
  con el tag `"bundle"` se saca, no tiene economía de venta propia real.
- **Solo publicaciones `status: active`**.
- **Catálogo + tradicional duplicados**: cuando dos publicaciones activas comparten el mismo
  `user_product_id`, es el MISMO producto físico publicado dos veces (con distinto
  `listing_type` o precio). A diferencia de `stock_valorizado` (que se queda con la de
  **menor precio**), acá nos quedamos con la de **menor Recibís** -- confirmado con Lucas
  2026-09-15 que el precio de lista no predice el ingreso neto: un caso real dio Recibís
  $12.191 en la publicación de *mayor* precio (gold_pro, con más costo de financiación) contra
  $12.470 en la de *menor* precio (gold_special) del mismo producto. El objetivo de esta
  tabla es el peor caso real de ingreso, no el precio de lista más bajo.
- **Una fila por publicación por día** -- correr esto más de una vez el mismo día
  **reemplaza** la foto de ese día (no duplica), nunca toca fotos de días anteriores.
- Si una publicación con envío gratis no tiene dimensiones/peso cargados, el script imprime
  una advertencia y deja el envío absorbido en 0 (subestima el Recibís real) -- no es un
  error que frene la corrida, pero conviene avisarle a Lucas si aparece.

## Cuándo correr esto

Pensada para correr todos los días como parte de `/actualizar-tablero`, igual que
`stock_valorizado`. Si Lucas pregunta "¿cuánto recibía tal día por tal publicación?" y esa
fecha no está en `publicaciones_recibis.json`, avisarle que no hay foto guardada de ese día.
