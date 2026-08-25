---
name: actualizar-base-envios
description: "Actualiza la pestaña 'base_envios' del Google Sheet de Deleite (MercadoLibre) -- una fila por orden pagada con Shipment_id, Tipo de envío, Ingreso/Costo por envío, en pesos con y sin IVA. Usar SIEMPRE que Lucas pida actualizar, completar o correr base_envios, o pida 'la tabla de envíos', 'el detalle de envío por orden' -- incluso si no menciona el nombre exacto de la pestaña."
---

# Actualizar base_envios (Deleite / MercadoLibre)

Repo: `C:\Users\User\Projects\mercadolibre`. Todos los comandos se corren parados ahí.

`base_envios` es la contracara de `base_ventas` (misma granularidad, una fila por orden pagada) pero enfocada solo en la economía del envío -- no en toda la venta. Ver memoria `mercadolibre-base-envios` para el detalle completo.

## Paso 1 -- reportar cobertura y pedir el rango

```bash
python fetch_orders.py --status
```

Decirle a Lucas hasta qué fecha hay datos y qué rango quiere actualizar.

## Paso 2 -- asegurar que las órdenes estén cacheadas

```bash
python fetch_orders.py <mes> <fecha_desde> <fecha_hasta>
```

## Paso 3 -- calcular base_envios para los días a actualizar + 1 día de margen

```bash
python compute_base_envios.py <order_id_1> <order_id_2> ... <order_id_n>
```

**Pasar juntas, en un solo comando, todas las `order_id` de los días nuevos MÁS el día calendario anterior al primero** -- igual que en `base_ventas`, el script agrupa por `shipment_id` para prorratear entre órdenes hermanas de un mismo pack, y eso solo funciona si se procesan juntas en la misma corrida. **No hace falta reprocesar todo el mes**: confirmado empíricamente (2026-07-31) que ningún shipment compartido cruza fechas distintas -- las hermanas de un pack siempre se crean el mismo día calendario. Un día de margen hacia atrás alcanza.

```bash
python -c "import json; print(' '.join(str(o['id']) for o in json.load(open('ordenes_<mes>.json', encoding='utf-8')) if '<fecha_desde_menos_1>' <= o['date_created'][:10] <= '<fecha_hasta>'))"
```

API-call-heavy, pero acotado a pocos días -- si igual demora, correrlo en background y avisar cuando termine.

## Paso 4 -- subir al Sheet

```bash
python build_base_envios_sheet.py
```

Limpia la pestaña antes de escribir, así que es seguro re-correrlo aunque cambie la cantidad de filas.

## Paso 5 -- reportar

Cuántas órdenes entraron, cuántas quedaron afuera por no estar `paid`, y si hubo algún shipment compartido prorrateado.

## Reglas de metodología -- no re-derivar

- **Solo `status == "paid"`.**
- **Ingreso por envío** = si `logistic_type == "self_service"` (Flex), de `/shipments/{id}/costs` (`receiver.cost -> senders[0].save -> gross_amount`). **También** si es Full/Colecta CON un cargo real en `charges_details` pero `senders[0].cost == 0` en `/shipments/{id}/costs` -- ese cargo es un pasante financiado por el comprador (confirmado 2026-07-28 contra `net_received_amount` real y la pantalla de Lucas: se ve como "Pago de Mercado Envíos" + "Cargo por Envíos de ML" cancelándose) y hay que cargarlo como Ingreso igual al Costo para que se anulen, en vez de dejarlo como costo real.
- **Costo por envío** = `charges_details` `type=="shipping"` del pago (solo aparece cuando es un costo real -- Full suele lavar a $0, y a veces ni aparece en `charges_details`). Si aparece pero es el pasante descripto arriba, igual queda cargado como Costo (para que se vea el movimiento completo, como en la pantalla real), pero con el Ingreso que lo cancela al lado.
- Ambos vienen **con IVA** tal cual de la API; la versión `s/IVA` es una división directa por 1,21 (acá no hay excepciones como en `base_ventas` -- ni impuestos ni costo de mercadería que compliquen la regla).
- **Mismo prorrateo por shipment compartido que `base_ventas`** -- solo funciona bien si todas las órdenes del período se procesan en la misma corrida.
- `Order_id`/`Pack_id`/`Shipment_id` se escriben como texto en el Sheet (prefijo `'`).

Ver memoria `mercadolibre-base-envios` para el detalle completo y los casos reales que motivaron cada regla.
