---
name: mercadolibre-base-envios
description: "How to build/update the 'base_envios' tab (Google Sheet) -- one row per paid order with Shipment_id, Tipo de envío, Ingreso/Costo por envío, con IVA and sin IVA."
metadata:
  node_type: memory
  type: project
  originSessionId: 970f6866-df46-44f9-916d-e89be8e46854
  modified: 2026-07-28T20:30:38.556Z
---

Companion tab to [[mercadolibre-base-ventas]], same Sheet -- same order-level granularity but focused only on shipping economics (not the whole sale cascade). Built and validated with 5 real order IDs before confirming the structure.

**Why:** Lucas wanted the shipping side isolated from the product/commission side, presumably to analyze logistics economics on its own.

## Scripts

- `compute_base_envios.py <order_id> [<order_id> ...]` -- pass ALL order_ids for a period in one run (same shared-shipment proration constraint as `compute_base_ventas.py` -- see that memory file for why). Writes/merges `base_envios.json`.
- `build_base_envios_sheet.py` -- clears + rewrites the `base_envios` tab (same clear-before-write pattern as base_ventas, to avoid stale leftover rows).

## Columns

`Order_id, Pack_id, Fecha, Shipment_id, Tipo de envío, Ingreso por envío, Ingreso por envío s/IVA, Costo por envío, Costo por envío s/IVA`

- `Order_id`/`Pack_id`/`Shipment_id` written as text (apostrophe prefix) -- same reason as base_ventas, avoids Excel mangling big IDs.
- Only `status == "paid"` orders (same filter, same reasoning as base_ventas).
- **Ingreso por envío** = when `logistic_type == "self_service"` (Flex), from `/shipments/{id}/costs` (`receiver.cost -> senders[0].save -> gross_amount`). **Also** set (equal to Costo, so they cancel) for Full/Colecta when the shipping charge turns out to be a buyer-funded pass-through -- see the "Buyer-funded shipping pass-through" section in [[mercadolibre-base-ventas]] for the full story (found 2026-07-28, real bug affecting historical data, fixed retroactively). Check: `senders[0].cost == 0` in `/shipments/{id}/costs` means it's a pass-through, not a real cost.
- **Costo por envío** = `charges_details` `type=="shipping"` from the order's payment (real cost only -- Full commonly washes to $0 with nothing even in `charges_details`; a nonzero entry here can STILL be a wash if `senders[0].cost == 0`, see above).
- Both come **con IVA** as-is from the API; the `s/IVA` columns divide by 1.21. (Unlike `base_ventas`, there's no tax/COGS line here to complicate the con/sin-IVA rule -- straightforward division both ways.)
- **Same shared-shipment proration as base_ventas**: if a pack's orders share one `shipment_id`, both ingreso and costo are prorated across siblings by each order's `importe` share -- only correct when the whole batch is processed together in one script invocation.

## Validated with (2026-07-23)

5 real orders spanning the three cases: Full washing to $0 both sides, Flex with real ingreso, Full with a real egreso cost. No shared shipment in that sample, but the proration logic is implemented and mirrors `compute_base_ventas.py`.

## Full historical build done (2026-07-23)

Ran mayo/junio/julio (360 paid orders total, same 1 partially_refunded May order excluded as in base_ventas). Hit a real bug mid-run: the access token expired partway through the June batch (`requests.exceptions.HTTPError: 401` on a `mercadopago.com` call) and crashed the whole run -- **fixed by adding automatic token refresh on any 401 inside `get()`**, not just at start-of-script via `get_token()`. This matters because these are long-running scripts (100+ orders, several minutes) and the token can expire mid-run. Applied the same fix to `compute_base_ventas.py` too. If writing a new long-running MercadoLibre/MercadoPago script, copy this `get()` pattern (refresh-and-retry-once on 401) rather than only checking the token at startup.
