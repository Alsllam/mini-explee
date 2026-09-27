"""Show what the program will actually use, without calling the API.

Run from the project root:
    python -m scripts.check_env

It never prints your key: only its first 3 characters and its length.
"""
import os
from pathlib import Path

import config

print("Project folder :", Path.cwd())
print(".env file used :", config.ENV_FILE or "NOT FOUND  <-- create .env in the project folder")

# Windows often hides extensions, so ".env" saved from Notepad becomes ".env.txt".
for wrong in (".env.txt", "env", ".env.example.txt"):
    if Path(wrong).exists():
        print(f"WARNING        : found '{wrong}' - rename it to exactly '.env'")

key = os.getenv("OPENAI_API_KEY") or ""
if not key:
    print("API key        : MISSING")
else:
    kind = "OpenAI key (sk-...)" if key.startswith("sk-") else "not an sk- key (Azure keys look like this)"
    print(f"API key        : {key[:3]}*** ({len(key)} chars) -> {kind}")

base = config.OPENAI_BASE_URL
if base is None:
    print("Endpoint       : https://api.openai.com/v1  (OpenAI - OPENAI_BASE_URL is empty)")
else:
    print("Endpoint       :", base)
    if "azure" in base and not base.rstrip("/").endswith("/openai/v1"):
        print("WARNING        : Azure URL should end with /openai/v1/")

tavily = os.getenv("TAVILY_API_KEY") or ""
if not tavily or tavily == "tvly-...":
    print("Tavily key     : not set (only needed for --web tavily)")
else:
    ok = "ok" if tavily.startswith("tvly-") else "WARNING: Tavily keys start with tvly-"
    print(f"Tavily key     : {tavily[:5]}*** ({len(tavily)} chars) {ok}")

for task, model in config.MODELS.items():
    print(f"Model [{task:9}]:", model)

if base and key.startswith("sk-"):
    print("\nWARNING: Azure endpoint with an sk- key. Use the Azure key from 'Keys and Endpoint'.")
if base is None and key and not key.startswith("sk-"):
    print("\nWARNING: this looks like an Azure key but OPENAI_BASE_URL is empty,")
    print("         so requests go to OpenAI. Set OPENAI_BASE_URL in .env.")
