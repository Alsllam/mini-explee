"""List the models your API key can use (lesson 1.5).

Run from the project root:
    python -m scripts.list_models          # all models
    python -m scripts.list_models mini     # only ids containing "mini"
"""
import sys

from core.client import get_client

keyword = sys.argv[1].lower() if len(sys.argv) > 1 else ""
ids = sorted(m.id for m in get_client().models.list() if keyword in m.id.lower())

for model_id in ids:
    print(model_id)
print(f"\n{len(ids)} model(s)")
