---
name: actualizar-balance-salida
description: "Actualiza la pestaña 'balance_salida' del Google Sheet de Deleite (MercadoLibre) -- si Lucas vendiera TODO el stock activo hoy, con cuánta plata le queda después de descontar autónomos, IIBB, percepciones/retenciones y deudas pendientes de pago. Usar SIEMPRE que Lucas pida el 'balance de salida', cuánta plata le queda si vende todo, o su liquidez real hoy -- incluso si no menciona el nombre exacto de la pestaña."
---

# Actualizar balance_salida (Deleite / MercadoLibre)

Repo: raíz del checkout de `ledelsztein/mercadolibre`. Todos los comandos se corren parados ahí.

Tabla nueva (2026-09-16, pedido de Lucas). Premisa: *"si mañana vendo todo, ¿con cuánta
plata me queda descontando los gastos fijos y el dinero que tengo que devolver?"*

```
Balance de Salida = Total Stock Recibido
                     - Autónomos (último pago cargado)
                     - IIBB (último pago cargado)
                     - Percepciones y Retenciones (último período de base_impositiva)
                     - Deudas pendientes de pago a la fecha
```

## Requisitos previos -- correr en este orden

Este cálculo depende de que otras tablas estén frescas. **Correr `date +%Y-%m-%d` primero**
si hay duda de qué día es hoy.

```bash
python compute_publicaciones_recibis.py   # si no se corrió ya hoy
python compute_stock_valorizado.py        # si no se corrió ya hoy (solo referencia, no afecta el balance)
python compute_balance_salida.py
python build_balance_salida_sheet.py
```

Si `publicaciones_recibis.json` o `stock_valorizado.json` no tienen una foto de hoy,
`compute_balance_salida.py` igual corre pero imprime una ADVERTENCIA y usa la foto más
reciente disponible -- avisarle a Lucas si eso pasa, no asumir que está bien.

## De dónde sale cada número -- no re-derivar

- **Total Stock Recibido**: suma de `recibis_total` (Recibís por unidad × stock disponible)
  de la foto más reciente en `publicaciones_recibis.json`. Este es el número que realmente
  resta el balance -- `Total Stock Valorizado` (de `stock_valorizado.json`, precio de lista
  sin descontar nada) se muestra solo de referencia al lado, no se usa en la resta.
- **Autónomos / IIBB**: de `base_informativa.json`, categorías `Autónomos` e `IIBB` -- se
  toma la fila con la **fecha más reciente** de cada una. Es un pago único (no se suman
  todos los pagos históricos): representa el próximo vencimiento a afrontar, no el gasto
  acumulado del año.
- **Percepciones y Retenciones**: de `base_impositiva.json`, se toma el `period_key` más
  reciente y se suman TODAS sus filas (son varias líneas por grupo/jurisdicción/categoría
  de impuesto dentro de un mismo período).
- **Deudas pendientes**: **única tabla del pipeline donde el Google Sheet es la fuente
  primaria**, no un JSON local -- la pestaña `deudas_pendientes` la carga Lucas a mano,
  directo en el Sheet. Columnas: `Fecha de la deuda` | `Concepto` | `Monto` | `Fecha de
  pago` (vacío = sigue pendiente). Una fila cuenta como deuda pendiente a la fecha F si
  `fecha_deuda <= F` Y (`fecha_pago` vacía O `fecha_pago > F`) -- ver docstring de
  `compute_balance_salida.py` para el caso real que motivó esta regla (un cheque que fue
  deuda solo durante los días entre emisión y pago, no antes ni después).

## Si Lucas quiere cargar una deuda nueva

No hay script para esto -- decirle que la cargue directo en la pestaña `deudas_pendientes`
del Sheet (tiene notas en los encabezados explicando cada columna). Cuando la pague, no
debe borrar la fila -- completar `Fecha de pago` para que quede como historial y salga del
cálculo de deuda pendiente a partir de esa fecha.

## Cuándo correr esto

Pensada para correr todos los días como parte de `/actualizar-tablero`, después de
`publicaciones_recibis` y `stock_valorizado` (depende de ambas). Si Lucas pregunta "¿cuál
era mi balance de salida tal día?" y esa fecha no está en `balance_salida.json`, avisarle
que no hay foto guardada de ese día.
