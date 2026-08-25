---
name: actualizar-base-ventas
description: "Actualiza la pestaña 'base_ventas' del Google Sheet de Deleite (MercadoLibre) -- una fila por orden pagada con Precio/Importe/Cargos/Impuestos/Costo/Resultado Neto, en pesos con y sin IVA. Usar SIEMPRE que Lucas pida actualizar, completar, correr o cargar base_ventas, o pida 'la tabla base' / 'el detalle por orden' / 'la planilla orden por orden' de Deleite -- incluso si no menciona el nombre exacto de la pestaña. También usar si pide agregar un rango de fechas nuevo a esa tabla, o re-verificar/corregir filas ya cargadas."
---

# Actualizar base_ventas (Deleite / MercadoLibre)

Repo: `C:\Users\User\Projects\mercadolibre`. Todos los comandos de este skill se corren parados ahí.

`base_ventas` es un libro mayor: una fila por **orden pagada**, con el desglose completo de la venta (Precio, Importe, Cargos, Impuestos, Costo, Resultado Neto), cada monto en su versión con IVA y sin IVA. Es la fuente granular que respalda al P&L agregado -- no se toca la metodología sin que Lucas lo pida explícitamente, porque salió de varias rondas de corrección suya contra ventas reales.

## Paso 1 -- reportar cobertura y pedir el rango

Nunca reprocesar todo el histórico sin que Lucas lo pida. Correr primero:

```bash
python fetch_orders.py --status
```

Decirle a Lucas hasta qué fecha hay datos, y preguntarle qué rango quiere actualizar (mismo criterio que el resto del pipeline de Deleite).

## Paso 2 -- asegurar que las órdenes estén cacheadas

```bash
python fetch_orders.py <mes> <fecha_desde> <fecha_hasta>
```

Mergea por `order_id` en `ordenes_<mes>.json`, sin duplicar (ver el script si hace falta el detalle).

## Paso 3 -- calcular base_ventas para los días a actualizar + 1 día de margen

```bash
python compute_base_ventas.py <order_id_1> <order_id_2> ... <order_id_n>
```

**Pasar juntas, en un solo comando, todas las `order_id` de los días nuevos MÁS el día calendario anterior al primero.** El script agrupa las órdenes por `shipment_id` para prorratear el envío entre hermanas de un mismo pack -- si se corre incrementalmente sin las hermanas, una orden vieja ya guardada no se vuelve a prorratear cuando aparece su hermana nueva. **No hace falta reprocesar todo el mes**: se confirmó empíricamente (2026-07-31, 27 shipments compartidos revisados en mayo/junio/julio) que ningún shipment compartido cruza fechas distintas -- las órdenes de un mismo pack siempre se crean el mismo día calendario, porque nacen de una sola compra. Un día de margen hacia atrás alcanza como colchón; no hace falta ir más atrás.

Para sacar la lista de `order_id` de esos días (del mes ya cacheado):

```bash
python -c "import json; print(' '.join(str(o['id']) for o in json.load(open('ordenes_<mes>.json', encoding='utf-8')) if '<fecha_desde_menos_1>' <= o['date_created'][:10] <= '<fecha_hasta>'))"
```

Si Lucas da un ID para revisar puntualmente y no aparece con `GET /orders/{id}`, es casi siempre un `pack_id`, no un `order_id` -- buscarlo en el `ordenes_<mes>.json` correspondiente por el campo `pack_id` para encontrar la orden real.

Esto pega bastante a la API de MercadoLibre/MercadoPago (2-3 llamados por orden) -- para un mes completo puede tardar varios minutos; correrlo en background y avisar a Lucas cuando termine, no quedarse esperando en silencio.

## Paso 4 -- subir al Sheet

```bash
python build_base_ventas_sheet.py
```

Lee `base_ventas.json` y reescribe la pestaña `base_ventas` completa (agrupada por pack, sin filas de total -- ver abajo). El script ya limpia la pestaña antes de escribir, así que es seguro correrlo de nuevo aunque el período anterior haya tenido más o menos filas.

## Paso 5 -- reportar, no solo decir "listo"

Contarle a Lucas: cuántas órdenes entraron, cuántas quedaron afuera por no estar `paid` (el script las imprime), y si hubo algún shipment compartido por varias órdenes que se prorrateó. Son las tres cosas que él mismo pidió poder verificar.

## Reglas de metodología -- no re-derivar, no cambiar sin que Lucas lo pida

Estas reglas salieron de rondas de corrección de Lucas contra ventas reales. Si algo no cierra, avisarle y preguntar -- no inventar una regla nueva por las tuyas.

- **Solo entran órdenes con `status == "paid"`** (`fetch_order_base()` en `compute_base_ventas.py` ya lo filtra e imprime cuáles excluye). Una orden `partially_refunded` puede tener el pago en `approved` y aun así no ser `paid` -- rompe toda la cuenta si se incluye.
- **Cargos variables/fijos e Impuestos salen del pago (`charges_details` de MercadoPago), nunca de Facturación/Billing.** Se probó a fondo (bruto/descuento no existe en ningún lado de `/orders` ni `/payments`) y Facturación es poco confiable para órdenes recientes de un período todavía abierto -- por eso Lucas decidió no depender de ella acá. `meli_percentage_fee` = cargo variable, `flat_fee` = cargo fijo, `type=="tax"` = impuestos (percepción/retención, ej. IIBB). Estos montos ya vienen netos de cualquier descuento de ML -- por eso **no hay columna de "Descuentos y bonificaciones"** en esta tabla (se sacó a propósito).
- **Con IVA vs sin IVA**: dividir por 1,21 para pasar a sin IVA -- Precio, Importe, Cargos variables, Cargos fijos, Cargos por envíos, Ingresos por envíos, Importe recibido, Resultado Neto. **No dividir** Impuestos de la operación (no está gravado) ni Costo de mercadería en su versión sin IVA (ya viene sin IVA de la planilla de Lucas -- la versión con IVA es la que se calcula como costo × 1,21, no al revés).
- **Envío**: cargo real = `charges_details` `type=="shipping"` (solo aparece cuando es un costo real -- Full muchas veces lava a $0, y a veces ni siquiera aparece en `charges_details`). Ingreso: si es Flex (`logistic_type=="self_service"`), sale de `/shipments/{id}/costs`. **Si es Full/Colecta y HAY un cargo real en `charges_details`, igual hay que chequear `/shipments/{id}/costs` antes de darlo por bueno**: si `senders[0].cost == 0` (Lucas no pone nada de su lado, `receiver.cost > 0` es el comprador quien paga), ese cargo es un **pasante financiado por el comprador** que se cancela solo -- en la pantalla real de Lucas aparece como dos líneas que se anulan ("Pago de Mercado Envíos" + "Cargo por Envíos de ML", ambas "a cargo del comprador"), pero eso no se ve en la API de pagos, solo en `/shipments/{id}/costs`. Confirmado con `net_received_amount` real en varios casos (2026-07-28): cuando `senders[0].cost == 0`, el cargo NO se descuenta de lo que Lucas cobra, así que hay que cargarlo como Ingreso además de Cargo (mismo monto, se cancelan) en vez de contarlo como costo real. Si `senders[0].cost > 0`, es un costo genuino, se deja como está. Si el shipment lo comparten varias órdenes del mismo pack, cargo e ingreso se prorratean entre ellas por el peso de cada una en el importe total del shipment -- no se le atribuye entero a la orden que casualmente cargó el cobro.
- **Importe recibido no siempre es igual al `net_received_amount` de la API del pago** -- es una cascada construida (Importe − cargos − cargo envío + ingreso envío − impuestos). Con Flex, el ingreso del envío se liquida aparte (no en el pago de esa orden puntual), así que el `net_received_amount` de la API por sí solo lo excluye.
- **Margen Neto sin Flex**: solo se completa cuando el tipo de envío es Flex (`Resultado Neto − Ingresos por envíos`) -- para Full/Colecta esas columnas quedan vacías, no en $0.
- **`Orden_id`/`Pack_id` se escriben como texto** en el Sheet (prefijo `'` antes del número) para que Excel/Sheets no los rompa.
- **Sin filas de total ni subtotal dentro de `base_ventas`** -- Lucas la quiere estrictamente una fila por orden; la consolidación se hace en otro lado.

Para el detalle completo de por qué se llegó a cada una de estas reglas (incluyendo los casos reales que las motivaron), ver la memoria `mercadolibre-base-ventas` si está disponible, o preguntarle a Lucas si algo no queda claro -- mejor preguntar que asumir.
