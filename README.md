# mercadolibre

Pipeline de P&L (Google Sheet + dashboard HTML) para Deleite, la cuenta de
MercadoLibre/MercadoPago de Lucas Edelsztein (seller DELEITEMP, seller_id
42206571, sitio MLA). Arma 8 tablas base_* desde las APIs de MercadoLibre,
MercadoPago y Facturación, y con eso genera un P&L recurrente publicado como
Google Sheet + dashboard.

- **Setup en una compu nueva**: ver [SETUP.md](SETUP.md).
- **Cómo se arma el pipeline, reglas de cada tabla, decisiones ya validadas**: ver [docs/memoria/](docs/memoria/).
- **Actualizar el tablero**: skill `actualizar-tablero` en `.claude/skills/` (invoca a las 7 skills `actualizar-base-*`).
- **Monitoreo de precios de mayoristas**: skill `monitorear-mayorista-enm` en `.claude/skills/` -- corre diario (trigger programado) y avisa si cambia un precio o desaparece un ítem de la lista del mayorista ENM. Snapshots en `monitoring/`.

Repo conectado a Claude Code.
