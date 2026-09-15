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
