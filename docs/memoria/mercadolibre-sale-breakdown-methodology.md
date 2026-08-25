---
name: mercadolibre-sale-breakdown-methodology
description: "How to correctly break down a MercadoLibre sale (commission + shipping) into a real net amount that matches Lucas's own \"Detalle de cobro\" screen."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 970f6866-df46-44f9-916d-e89be8e46854
  modified: 2026-07-21T17:21:19.115Z
---

When Lucas gives a MercadoLibre order/pack ID and asks to break down a sale, use this methodology. It went through several rounds of correction — an earlier version of this rule (a cascading formula over `/shipments/{id}/costs` fields, treating shipping as an added positive) was **wrong** and got overturned by real screenshots of his "Detalle de cobro". Do not reintroduce that cascading rule.

**Why:** Lucas said "no quiero que asumas nada, solo trae la información que tengas" and later, after I kept inventing shipping rules that broke on new cases, gave the actual master rule: always check against `net_received` — if my calculation matches it, it's correct; if not, something is missing and I need to dig further, not assume.

**How to apply:**

1. **ID lookup**: The ID Lucas gives is usually a `pack_id`, not an `order_id` — `GET /orders/{id}` will 404. Search `GET /orders/search?seller={user_id}&order.date_created.from={date}&sort=date_desc` and filter results client-side for `pack_id == <id>`. Widen the date range (up to ~180 days) rather than asking him first. A pack can contain 1 or more orders (kit components) sharing one `shipping.id`.
2. **The ground truth is `net_received`**: Call `GET https://api.mercadopago.com/v1/payments/{payment_id}` (note: mercadopago.com domain, not mercadolibre.com — the `/orders/{id}` payment sub-object's `order.order_items[].sale_fee` field does NOT match the real charge, ignore it). Read `charges_details` (list of `{name, amounts.original}`) and `amounts.collector.net_received` (older payment schema instead uses `transaction_details.net_received_amount` — check which key exists).
3. **`venta_total - sum(charges_details) == net_received` always holds by construction.** This is the final answer in the vast majority of cases. Common `charges_details` names seen: `meli_percentage_fee`, `flat_fee`, and — only when shipping is a genuine extra cost — `shp_fulfillment`.
4. **Do NOT go hunting for extra shipping adjustments** in `/shipments/{id}/costs` or in the Billing API and add/subtract them yourself. Confirmed by side-by-side comparison with real screenshots: when a shipping-related figure shows up in `/shipments/{id}/costs` (`receiver.cost`, `gross_amount`, etc.) or even as a real "Cargo por envíos de Mercado Libre" charge in the Billing API (`marketplace_info: "SHIPPING"`), but it is **not** present inside the payment's own `charges_details` — it is a wash. On his real "Detalle de cobro" it always shows up as a matching positive line ("Pago de Mercado Envíos") and negative line ("Cargo por Envíos... a cargo del comprador") that cancel to exactly $0. `net_received` already reflects this correctly (i.e. reflects nothing, since it's zero-sum) — do not adjust it further.
5. **When shipping IS a real cost**, it appears directly inside `charges_details` as its own entry (e.g. `shp_fulfillment`) and is already subtracted in `net_received` — again, no extra step needed beyond reading `charges_details`.
6. **Discounts/employee pricing**: `payments.charges_details` amounts (`meli_percentage_fee`, `flat_fee`) are already net-of-discount. To explain *why* a fee is lower than the category's list percentage, check the Billing API (`GET /billing/integration/periods/key/{key}/group/ML/details?document_type=BILL&order_ids={order_id}`) — each entry's `discount_info` has `charge_amount_without_discount`, `discount_amount`, and `discount_reason` (e.g. `"Descuento para empleados"` = 50% employee discount seen on several sales). Good for desagregar/explain, not for adjusting the total.
7. **The billing period key** covering "now" during this session was `2026-08-01` (date_from 2026-07-07); older sales may fall in earlier CLOSED periods — list via `GET /billing/integration/monthly/periods?group=ML&document_type=BILL` to find the right key.

**Bottom line**: compute `venta_total - sum(payment.charges_details)`, confirm it equals `net_received`, present that as the final neto. Only if it does NOT match `net_received` should further investigation happen (and even then, don't invent a formula — find the actual missing `charges_details` entry or flag the discrepancy to Lucas).

Other gotchas hit along the way:
- Order/payment JSON shapes vary (e.g. presence of `financing_group`, `amounts.collector.net_received` vs `transaction_details.net_received_amount`) — check keys defensively, don't assume one fixed shape.
- API is rate-limited (`local_rate_limited` 429) — add a short sleep and retry rather than treating it as a hard failure.
- Once Lucas said "acepto todo, no hace falta pedirme permiso de consulta" for read-only lookups on his own sales data — proceed straight to fetching for subsequent sale IDs without asking first.

See also [[mercadolibre-project-setup]] for where the code/credentials live.
