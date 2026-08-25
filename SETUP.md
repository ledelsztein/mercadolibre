# Setup en una computadora nueva

1. `git clone https://github.com/ledelsztein/mercadolibre.git` y pararse en esa carpeta.
2. Python 3.12+, y las libs: `pip install requests python-dotenv google-auth google-auth-oauthlib google-api-python-client openpyxl`.
3. Crear `.env` en la raíz del repo (gitignored, no viene en el clone) con:
   ```
   ML_CLIENT_ID=4896067406062685
   ML_CLIENT_SECRET=<pedirle a Lucas>
   ML_REDIRECT_URI=https://www.google.com
   GOOGLE_CLIENT_ID=<pedirle a Lucas>
   GOOGLE_CLIENT_SECRET=<pedirle a Lucas>
   ```
4. Autenticar MercadoLibre: correr `auth.py` (abre el navegador, pide pegar el `code` de la URL de redirect — la app requiere PKCE). Genera `token.json` (gitignored, se refresca solo después via `refresh_token`).
5. Autenticar Google: correr `auth_google.py` (login interactivo por navegador). Genera `google_token.json` (gitignored).
6. Listo — `sheet_id.txt` y `data/Costos.xlsx` ya vienen en el repo, así que `/actualizar-tablero` debería correr de punta a punta sin más setup.

Detalle completo (por qué PKCE, qué app de MercadoLibre, etc.) en
[docs/memoria/mercadolibre-project-setup.md](docs/memoria/mercadolibre-project-setup.md).
