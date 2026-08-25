---
name: actualizar-base-full
description: "Actualiza la pestaña 'base_full' del Google Sheet de Deleite (MercadoLibre) -- una fila por día con los cargos de Fulfillment (Full) que MercadoLibre cobra por Facturación y que no aparecen en ninguna otra tabla: colecta Full (envío al depósito) y almacenamiento Full, con y sin IVA. Usar SIEMPRE que Lucas pida actualizar, completar o correr base_full, o pida 'los cargos de Full', 'el almacenamiento Full', 'la colecta Full' -- incluso si no menciona el nombre exacto de la pestaña."
---

# Actualizar base_full (Deleite / MercadoLibre)

Repo: `C:\Users\User\Projects\mercadolibre`. Todos los comandos se corren parados ahí.

Tabla nueva (2026-07-31, pedido de Lucas): cargos de Fulfillment que NO están capturados en ningún otro lado del pipeline. Igual que `base_ads`, **no necesita order_ids** -- siempre se llama con el rango completo mayo-hoy, y el script (`compute_base_full.py`) cachea agresivamente (mismo patrón que `base_ads`, ver esa skill).

**Ojo, error real cometido y corregido el mismo día (2026-07-31)**: la primera versión de esta tabla usaba `CFF` pensando que era "envío Full" -- daba ~$611K para julio, un número absurdo. Lucas lo marcó comparando contra su factura real de Mercado Libre y se confirmó: `CFF` (+ `CXD`) es la línea general **"Cargos de envíos de Mercado Libre"**, no tiene nada de específico a Full (matchea exacto: `CFF + CXD` = esa línea de la factura, verificado en dos facturas distintas). El código real de Full es otro (`CFCB`, ver abajo) que ni siquiera existía en la primera versión. Si en algún momento hay que tocar esta tabla de nuevo, **verificar siempre contra una factura real de Lucas antes de confiar en una hipótesis de mapeo de código -- el nombre de un `detail_sub_type` o su `transaction_detail` no alcanza, hay que cruzar el monto agregado contra lo que la factura muestra**.

## Paso único -- recalcular y subir

```bash
python compute_base_full.py 2026-05-01 <fecha_hasta_hoy>
python build_base_full_sheet.py
```

**Antes de definir `<fecha_hasta_hoy>`, correr `date +%Y-%m-%d` para confirmar la fecha real del sistema.**

## Reglas de metodología -- no re-derivar

- **Fuente: Facturación (Billing API), grupo `ML`, marketplace `SHIPPING`.**
- **Colecta Full** (envío de mercadería al depósito de Mercado Libre) = `detail_sub_type` `CFCB` ("Cargo por servicio de colecta Full") + `BFCB` (reversa, si aparece).
- **Almacenamiento Full** = `detail_sub_type` `CFWA` ("Cargo por servicio de almacenamiento Full") + `BFWA` (reversa, si aparece).
- **`CFCB + CFWA` juntos son exactamente la línea "Cargos de envíos full" de la factura de Mercado Libre** -- verificado al centavo contra dos facturas reales de Lucas (julio cerrado: $596,40 = solo `CFWA`, `CFCB` no tenía entradas todavía ese período; agosto abierto: $52.700,69 = $48.587,69 `CFCB` + $4.113,00 `CFWA`). En el P&L quedan como DOS líneas separadas (pedido de Lucas) -- "Cargo por colecta Full" y "Cargo por almacenamiento Full" -- no una sola combinada.
- **`CFF`/`CXD` (mismo marketplace `SHIPPING`) NO son de Full** -- son la línea general "Cargos de envíos de Mercado Libre" de la factura (`CFF + CXD` matchea esa línea exacto). No incluir en esta tabla.
- **Tratado como Costo Variable** en el punto de equilibrio del P&L (pedido explícito de Lucas, 2026-07-31) -- ambas líneas (`cargo_colecta_full`, `cargo_almacenamiento_full`) se suman en `build_pnl_data.py`/`build_dashboard_data.py`/`build_sheet.py` a `costos_variables` y a `total_egresos`.
- **Con IVA vs sin IVA**: los montos de Facturación vienen CON IVA -- división directa por 1,21 para sin IVA, sin excepciones (igual que `base_ads`).
- **Cache agresivo**: un período se marca "cerrado" en cuanto deja de ser el período abierto de "hoy" y nunca se vuelve a pedir (cache en `base_full_cache_state.json`). Un período cerrado se cachea SIEMPRE, incluso sin ningún cargo Full ese período (mayo/junio 2026 no tuvieron ninguno) -- si dependiera de encontrar una factura real, un período sin cargos nunca se cachearía y se volvería a pedir para siempre (bug real encontrado y corregido 2026-07-31). Si algún número de un período ya cacheado resulta estar mal, borrar esa entrada de `periodos_cerrados` a mano para forzar un refetch.
- **Ojo con el límite de 90 días** de otras APIs de MercadoLibre -- Facturación en sí no lo tiene (paginado por período), no hace falta partir el rango acá.

Ver memoria `mercadolibre-pnl-pipeline` (sección "base_full / base_adelantos") para el contexto completo de por qué se armó esta tabla.
