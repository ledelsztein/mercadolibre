"""
Autenticacion OAuth2 con la API de MercadoLibre.

Uso:
    python auth.py

Genera token.json con el access_token y refresh_token.
"""
import base64
import hashlib
import json
import os
import secrets
import webbrowser

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ["ML_CLIENT_ID"]
CLIENT_SECRET = os.environ["ML_CLIENT_SECRET"]
REDIRECT_URI = os.environ["ML_REDIRECT_URI"]

TOKEN_URL = "https://api.mercadolibre.com/oauth/token"


def make_pkce_pair():
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return code_verifier, code_challenge


def main():
    code_verifier, code_challenge = make_pkce_pair()

    auth_url = (
        "https://auth.mercadolibre.com.ar/authorization"
        f"?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
        f"&code_challenge={code_challenge}&code_challenge_method=S256"
    )

    print("Abriendo el navegador para autorizar la app...")
    print(auth_url)
    webbrowser.open(auth_url)

    print(
        "\nDespues de aceptar, vas a terminar en una URL tipo:\n"
        f"  {REDIRECT_URI}/?code=TG-xxxxxxxx...\n"
        "Copia el valor de 'code' de esa URL."
    )
    code = input("\nPega aca el code: ").strip()

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        },
    )
    if not response.ok:
        print(f"\nError {response.status_code} de MercadoLibre:")
        print(response.text)
        response.raise_for_status()
    token_data = response.json()

    with open("token.json", "w") as f:
        json.dump(token_data, f, indent=2)

    print("\nListo. Token guardado en token.json")


if __name__ == "__main__":
    main()
