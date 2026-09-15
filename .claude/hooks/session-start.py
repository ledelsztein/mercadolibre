#!/usr/bin/env python3
"""
SessionStart hook: reconstruye .env, token.json y google_token.json
a partir de variables de entorno persistentes del entorno remoto,
para que el pipeline de MercadoLibre/Google no pida re-autenticar
en cada sesion nueva.

No debe romper nunca el arranque de la sesion: cualquier fallo
(env vars ausentes, refresh_token vencido, sin red) se ignora en
silencio y el pipeline avisa mas tarde si hace falta autenticar a mano.
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

os.chdir(os.environ.get("CLAUDE_PROJECT_DIR", "."))


def post_form(url, data):
    body = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in data.items())
    req = urllib.request.Request(url, data=body.encode(), method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def write_env_file():
    if os.path.exists(".env"):
        return
    keys = [
        "ML_CLIENT_ID",
        "ML_CLIENT_SECRET",
        "ML_REDIRECT_URI",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
    ]
    if not all(os.environ.get(k) for k in keys):
        return
    with open(".env", "w") as f:
        for k in keys:
            f.write(f"{k}={os.environ[k]}\n")


def write_ml_token():
    if os.path.exists("token.json"):
        return
    client_id = os.environ.get("ML_CLIENT_ID")
    client_secret = os.environ.get("ML_CLIENT_SECRET")
    refresh_token = os.environ.get("ML_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        return
    try:
        data = post_form(
            "https://api.mercadolibre.com/oauth/token",
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )
        with open("token.json", "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        # refresh_token de ML rota en cada uso: la copia persistida en el
        # entorno puede haber quedado vieja. El pipeline avisa mas tarde
        # si hace falta reautenticar a mano; no rompemos el arranque.
        pass


def write_google_token():
    if os.path.exists("google_token.json"):
        return
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        return
    try:
        data = post_form(
            "https://oauth2.googleapis.com/token",
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )
        expiry = (
            datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        google_token = {
            "token": data["access_token"],
            "refresh_token": refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": client_id,
            "client_secret": client_secret,
            "scopes": data.get("scope", "").split(),
            "universe_domain": "googleapis.com",
            "account": "",
            "expiry": expiry,
        }
        with open("google_token.json", "w") as f:
            json.dump(google_token, f, indent=2)
    except Exception:
        pass


def main():
    try:
        write_env_file()
    except Exception:
        pass
    try:
        write_ml_token()
    except Exception:
        pass
    try:
        write_google_token()
    except Exception:
        pass


if __name__ == "__main__":
    main()
