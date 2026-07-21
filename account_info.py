"""
Trae informacion de la cuenta de MercadoLibre usando el token guardado.

Uso:
    python account_info.py
"""
import json

import requests

with open("token.json") as f:
    token_data = json.load(f)

access_token = token_data["access_token"]

response = requests.get(
    "https://api.mercadolibre.com/users/me",
    headers={"Authorization": f"Bearer {access_token}"},
)
response.raise_for_status()

print(json.dumps(response.json(), indent=2, ensure_ascii=False))
