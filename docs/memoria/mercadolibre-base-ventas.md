---
name: mercadolibre-base-ventas
description: "How to build/update the 'base_ventas' tab (Google Sheet) -- one row per order with the full Precio/Importe/Cargos/Impuestos/Costo/Resultado Neto cascade, con IVA and sin IVA, validated with Lucas over several rounds."
metadata:
  node_type: memory
  type: project
  originSessionId: 970f6866-df46-44f9-916d-e89be8e46854
  modified: 2026-08-12T14:24:26.401Z
---

Lucas wants a granular, order-level ledger (`base_ventas` tab in the same Sheet as the P&L) so nothing gets lost in aggregation -- every order, every charge, tabulated. Built and validated row-by-row with him using real order IDs before running it on the full history. See [[mercadolibre-pnl-pipeline]] for the monthly/aggregate P&L this complements, and [[mercadolibre-sale-breakdown-methodology]] for the underlying commission-reading rules this reuses.

**Why:** "Me gustaría tener una tabla base donde vayamos poniendo toda la información, que no se nos salte nada de la cuenta" -- a persistent per-order source of truth, separate from the monthly aggregates.

## Scripts

- `compute_base_ventas.py <order_id> [<order_id> ...]` -- takes explicit **order_ids** (not pack_ids -- Lucas always gives pack_ids when spot-checking; look them up first via local `ordenes_<mes>.json` `pack_id` field, or if not cached, widen the search). Writes/merges into `base_ventas.json` (dict keyed by order_id as string). Two-phase: `fetch_order_base()` gets everything that's 100% the order's own (item, importe, cargo_var, cargo_fij, impuestos, costo, own shipment_id) without any cross-order dependency; then the `__main__` block groups fetched orders by `shipment_id` and prorates envío across siblings (see below) before calling `compute_row()`.
- `build_base_ventas_sheet.py` -- reads `base_ventas.json`, writes the `base_ventas` tab. **Always `values().clear()` the full range before `values().update()`** -- otherwise stale rows from a previous, longer run stick around below the new data (hit this bug once: a leftover "TOTAL_PACK" row kept reappearing because `update()` only overwrites the cells it sends, never shrinks the sheet).

## Column design (one row per order, con IVA block then sin IVA block)

`Orden_id, Pack_id, Fecha, ITEM_ID, SKU, Título producto, Cantidad, Tipo de envío` then, twice (con IVA / s/IVA): `Precio, Importe, Cargos variables (comisión), Cargos fijos, Cargos por envíos, Ingresos por envíos, Importe recibido, Costo de mercadería vendida, Resultado Neto, Margen Neto, Resultado Neto sin Flex, Margen Neto sin Flex`. `Impuestos de la operación (percepción/retención)` appears **once**, no con/sin-IVA split (it's a withholding, not subject to IVA).

- **`Orden_id`/`Pack_id` written as text** (`f"'{id}"` -- the leading apostrophe is the standard Sheets trick to force literal text under `USER_ENTERED`), otherwise Excel/Sheets mangles the big numeric IDs.
- **No totals/subtotal rows inside `base_ventas`** -- Lucas explicitly removed a "TOTAL_PACK" row he'd asked for at first ("después en la suma consolidamos todo" -- aggregation happens elsewhere, this tab is meant to stay one-row-per-order, granular).
- **Only `status == 'paid'` orders** go in (checked inside `fetch_order_base()`, returns `None` and the order is skipped with a printed warning if not). Found a real case: one May order was `partially_refunded` with `payments[0].status == 'approved'` -- it would have silently passed the older `is_valid()` filter in `fetch_orders.py` (which only excludes `cancelled`/`refunded`, not `partially_refunded`). `base_ventas` needs the stricter `paid`-only check since a partial refund breaks the whole cascade math.

## Where each field comes from -- deliberately NOT using Billing/Facturación

After a long back-and-forth, Lucas decided `base_ventas` should source **only from `/orders/{id}` and `/v1/payments/{id}`**, never Billing:

- **Cargos variables (comisión)** = `charges_details` `type=="fee"`, `name=="meli_percentage_fee"`.
- **Cargos fijos** = `charges_details` `type=="fee"`, `name=="flat_fee"`. (Any other `fee`-type entry with an unrecognized name is added to variable, not dropped.)
- **Impuestos de la operación** = `charges_details` `type=="tax"` (e.g. `tax_withholding-santa_fe`, an IIBB provincial withholding) -- available instantly per order, no Billing needed.
- Both of the above are **already net of any ML-side discount** (e.g. "Descuento para empleados") -- confirmed the bruto/descuento split genuinely does not exist anywhere in Orders or Payments (dumped both full JSON objects and grepped for discount/fee/coupon/marketplace_fee -- only Billing's `discount_info` has it, and Billing is unreliable for recent orders in an open period, see [[mercadolibre-pnl-pipeline]]). Lucas's final call: **drop the separate "Descuentos y bonificaciones" column entirely** and just use the net commission -- simpler, always available immediately, no dependency on Billing's processing lag.
- **Cargos por envíos** = `charges_details` `type=="shipping"` (only present when it's a real cost -- Full often washes to $0 with nothing even appearing in `charges_details`). **But a nonzero entry here isn't automatically a real cost either** -- see "Buyer-funded shipping pass-through" below, a second, different kind of wash discovered 2026-07-28.
- **Ingresos por envíos** = when `logistic_type == "self_service"` (Flex): `/shipments/{id}/costs`, `receiver.cost -> senders[0].save -> gross_amount` (first truthy wins). **Also** populated for Full/Colecta when the shipping charge turns out to be the buyer-funded pass-through described below.
- **Costo de mercadería**: con IVA = `costo_vigente_sin_iva() * 1.21`; sin IVA = as-is from Lucas's cost sheet (already sin IVA at the source -- do not divide it again).
- **Importe recibido** is a **constructed cascade** (`Importe - cargos - envío cargo + envío ingreso - impuestos`), not always literally equal to the order's own `net_received_amount` from the payment: when the shipment is Flex, the Flex income is settled through a *separate* payout, not through this order's own payment, so `net_received_amount` alone excludes it. `Importe recibido` in this table is the fuller "total real cash effect of the sale," Flex income included.

## Buyer-funded shipping pass-through -- a second kind of "wash", found 2026-07-28

The originally-documented shipping wash (a charge that shows up in `/shipments/{id}/costs` or Billing but is entirely absent from the payment's `charges_details`, netting to $0 with nothing to record) is NOT the only kind of wash. Lucas flagged two real orders (`2000017612519392`, `2000017620784950`) where `charges_details` DID have a genuine `type=="shipping"` entry (`shp_fulfillment`, nonzero, `"accounts": {"from": "collector", "to": "1319890380"}`) that the code was counting as a real cost -- but `net_received_amount` for both orders matched exactly when that shipping charge was **excluded**, proving it never actually reduced what Lucas got paid. Lucas then supplied a screenshot of his own "Detalle de cobro" for one of them: the Envíos section shows two lines that cancel to exactly $0 -- "Pago de Mercado Envíos (a cargo del comprador)" (+) and "Cargo por Envíos de Mercado Libre (a cargo del comprador)" (−) -- confirming it's buyer-funded, not Lucas's cost, even though only the negative side shows up in the API's `charges_details`.

**The distinguishing signal, found by comparing against a genuinely-charged same-day order**: check `/shipments/{id}/costs`.
- **Real cost to Lucas**: `senders[0].cost > 0` (his side of the shipment has a nonzero cost) -- the `charges_details` shipping entry is legitimate, leave it as Cargo, don't touch Ingreso.
- **Buyer-funded pass-through (wash)**: `senders[0].cost == 0` while `receiver.cost > 0` (the buyer's side carries the cost instead) -- even though a real charge appears in `charges_details`, it isn't Lucas's money. Fix: set **Ingreso por envío = the same amount as the Cargo**, so they cancel to $0 net (mirrors his screen showing both lines), rather than leaving Cargo as an uncancelled real expense.

This only matters when `total_egreso > 0` for a Full/Colecta shipment (i.e. there IS a `charges_details` shipping entry to begin with) -- if there's nothing in `charges_details`, that's still the original wash-with-nothing-to-record case and no extra shipment-costs lookup is needed. Implemented as an `elif total_egreso > 0:` branch alongside the existing `self_service` branch in `compute_base_ventas.py`'s (and `compute_base_envios.py`'s) shipment-grouping loop -- fetches `/shipments/{id}/costs` for these too now (previously only fetched for Flex), one extra API call per Full/Colecta shipment that has a real-looking charge.

**This was a real, retroactive bug affecting however many historical Full/Colecta orders hit this pattern** -- re-ran `compute_base_ventas.py`/`compute_base_envios.py` across all of mayo/junio/julio on 2026-07-28 after the fix to correct it everywhere, not just the two orders Lucas happened to spot. If a Full/Colecta order's margin looks suspiciously negative/low again in the future, this is the first thing to check (cross-reference `net_received_amount`, or ask Lucas for a "Detalle de cobro" screenshot like he did here -- it settled the question immediately).

## Envío proration when a pack has multiple orders sharing one shipment

Confirmed multi-order packs exist (e.g. pack with a Toalla order + a Toallón order sharing one `shipment_id`) -- ML sometimes puts the entire shipping charge on just one sibling's payment. Lucas's rule: **prorate both the shipping charge and the Flex income across siblings by each order's `importe` share of the shipment's total importe**, not attribute it 100% to whichever order happened to carry the charge.

Implementation constraint: **this proration only works correctly if all orders sharing a shipment are passed to `compute_base_ventas.py` in the same run.** Running it order-by-order across separate invocations will NOT retroactively re-prorate an already-saved sibling. For the full historical build, always pass a whole period's order list at once (like `compute_venta_detalle.py` already does), not incrementally one ID at a time.

## Con IVA vs sin IVA -- the exact rule

Divide by 1.21 for the sin-IVA version of: Precio, Importe, Cargos variables, Cargos fijos, Cargos por envíos, Ingresos por envíos, Importe recibido, Resultado Neto. **Do NOT divide**: Impuestos de la operación (not IVA-subject) and Costo de mercadería in its sin-IVA form (already sin IVA at the source -- the con-IVA form is the one that gets the ×1.21 instead). `Importe recibido s/IVA` is the **cascade of the already-divided lines**, not `net_received / 1.21` directly -- these differ by a few % because Impuestos isn't divided in either basis, confirmed and chosen deliberately (cascade wins, per Lucas).

## Margen Neto sin Flex

Only populated when `Tipo de envío == "Flex"` (`self_service`): `Resultado Neto sin Flex = Resultado Neto - Ingresos por envíos` (same subtraction in both con/sin IVA bases), `Margen Neto sin Flex = Resultado Neto sin Flex / Importe`. For Full/Colecta these four columns are `null`/blank -- not zero, genuinely not applicable. Purpose: see the product's real margin without the Flex delivery-income boost, since that income can double the apparent margin on some sales.

## Bug fixed 2026-08-12: fees must be summed across ALL approved payments, never just `payments[0]`

`fetch_order_base()` in both `compute_base_ventas.py` and `compute_base_envios.py` used to read `o['payments'][0]['id']` and pull `charges_details` only from that one payment. Lucas caught a real case (`2000017878778936`, cargo_var_c/cargo_fij_c both showing $0): the order had **two payment attempts** — a first one that was `rejected` (no charges_details at all) followed by an `approved` one that actually carried the fees, but `payments[0]` was the rejected attempt. A zero-cargo scan across all of `base_ventas.json` found a second, different case (`2000017174940148`, June): a single order **split across two payment methods**, both `approved`, where the fees landed entirely on the *second* payment, not the first.

**Fix**: loop over `o['payments']`, skip anything with `status != 'approved'`, and sum `charges_details` across every approved payment found (handles both the reject-then-retry case and the split-payment case with the same logic). Applied to both scripts.

**How to re-check for this after the fact**: scan `base_ventas.json` for rows where `cargo_var_c == -0.0 and cargo_fij_c == -0.0` — both known historical cases surfaced as a clean zero (payments[0] had literally nothing), so this scan is a fast way to catch it again if it recurs. A case where `payments[0]` has *some* but incomplete charges (rather than zero) would not be caught by this scan and hasn't been observed yet.

## Still pending as of 2026-07-23

Only ~3 orders processed as validation spot-checks. Full historical run (mayo through hoy) requested next -- run per-period (whole `ordenes_<mes>.json`, `status=='paid'` filtered) so shipment proration groups are complete, not order-by-order.
