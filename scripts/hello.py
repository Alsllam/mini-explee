"""Step 0 check: one real call through core.client.ask().

Run from the project root:
    python -m scripts.hello
"""
from core.client import ask

response = ask(
    "In two sentences, explain what a B2B sales outreach assistant does.",
    task="fast",
    instructions="You are a concise assistant. Answer in Arabic.",
)

print("Answer:\n" + response.output_text)
print("\nResponse id :", response.id)
print("Model       :", response.model)
print("Tokens in   :", response.usage.input_tokens)
print("Tokens out  :", response.usage.output_tokens)
print("\nA log line was added to logs/calls.jsonl")
