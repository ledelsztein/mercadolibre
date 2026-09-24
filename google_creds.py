"""
Credenciales de Google Sheets para todos los scripts del pipeline.

Orden de prioridad:
1. Service account desde la variable de entorno GOOGLE_SA_JSON (el contenido
   completo del JSON de la clave) -- pensado para los entornos cloud.
2. Service account desde el archivo google_sa.json (gitignored) -- uso local.
3. Fallback: OAuth de usuario desde google_token.json (auth_google.py).

La service account no vence ni requiere login por navegador; el Sheet de
Deleite tiene que estar compartido como Editor con su mail
(client_email del JSON).
"""
import json
import os

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SA_FILE = "google_sa.json"
OAUTH_FILE = "google_token.json"


def get_creds():
    sa_json = os.environ.get("GOOGLE_SA_JSON")
    if sa_json:
        return service_account.Credentials.from_service_account_info(
            json.loads(sa_json), scopes=SCOPES
        )
    if os.path.exists(SA_FILE):
        return service_account.Credentials.from_service_account_file(
            SA_FILE, scopes=SCOPES
        )
    return Credentials.from_authorized_user_file(OAUTH_FILE)
