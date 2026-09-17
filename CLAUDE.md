# Instrucciones para cualquier sesión de Claude Code en este repo

## Regla de oro: solo lectura sobre la cuenta de MercadoLibre

Este pipeline existe para **leer** datos de la cuenta de MercadoLibre de Lucas (ventas,
envíos, ads, facturación, stock, etc.) y volcarlos al Google Sheet de Deleite. No existe
para modificar nada en esa cuenta.

**Ninguna skill, script o sesión de Claude puede hacer un POST/PUT/PATCH/DELETE contra la
API de MercadoLibre que cree, modifique o borre algo real de la cuenta** — publicaciones,
precios, stock, pedidos, envíos, mensajes, configuración de la cuenta, etc. — **sin pedirle
autorización explícita a Lucas primero, para esa acción puntual.** Una autorización que dio
para una acción no cubre otra: hay que volver a preguntar cada vez que cambie la acción.

Esto vale aunque el `access_token` tenga scopes de escritura habilitados (los tiene, porque
vienen de cómo está registrada la app en developers.mercadolibre.com) — el límite lo pone
esta regla, no lo que el token técnicamente permite.

Los únicos llamados esperados contra la API de MercadoLibre en este repo son `GET` de
lectura (ver `fetch_orders.py`, los `compute_*.py`, `account_info.py`). Si en algún momento
una tarea pide explícitamente escribir algo en MercadoLibre (por ejemplo actualizar un
precio o un stock), primero hay que confirmar con Lucas el alcance exacto de esa escritura
puntual antes de tocar código o ejecutar nada — no asumir que el pedido general habilita
escrituras futuras.

## Sincronizar con `origin/main` antes de actualizar cualquier tabla

Lucas dispara actualizaciones de este pipeline desde varias sesiones distintas (terminal
local, sesiones cloud/PR, distintas ventanas de Claude Code) que no comparten estado entre
sí. Si una sesión corre sobre un checkout local desactualizado, recalcula desde una base
vieja, pierde datos que Lucas ya pasó en otra sesión (por ejemplo un monto de una tabla
informativa) y puede terminar pisando o duplicando trabajo ya mergeado. Pasó una vez
(sesión del 2026-09-17: el checkout local estaba 9 commits atrás de `origin/main`, con un
PR ya mergeado que traía el Autónomos de septiembre, mientras la sesión local tenía sin
commitear un cargo distinto -- Alan Jalef -- que el PR no tenía; hubo que reconciliar ambos
a mano).

**Por eso, antes de correr `actualizar-tablero` o cualquier `actualizar-base-*` puntual,
siempre correr primero:**

```bash
git fetch origin && git status
```

- Si el local está atrás de `origin/main` y puede hacer fast-forward limpio (sin cambios sin
  commitear que se pisen), actualizar con `git pull` antes de seguir.
- Si hay cambios sin commitear en archivos de datos (`base_*.json`, `pnl_data.json`,
  `dashboard_data.json`, etc.) que además difieren de `origin/main`, **no descartarlos a
  ciegas ni pisarlos con `git reset --hard`** sin antes diffear archivo por archivo contra
  `origin/main` -- puede haber datos reales (como el caso de Alan Jalef) que solo existen en
  un lado. Si algo diverge de verdad, avisarle a Lucas qué se encontró en cada lado antes de
  decidir qué conservar.
- Si el local y `origin/main` ya coinciden o el local está adelante (branch propia con commits
  nuevos), no hace falta hacer nada especial acá.
