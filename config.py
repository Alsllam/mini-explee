"""Central settings: one place for model names and limits (lessons 1.5 and 2.1).

Model names change often, so no other file in the project hardcodes them.
Every agent asks this module which model to use for its kind of task.
"""
import os

from dotenv import find_dotenv, load_dotenv

# Reads .env from the project root into environment variables (lesson 1.4).
# override=True: the project's .env wins over any OPENAI_* variable already set
# in Windows/macOS system settings, so what you see in .env is what runs.
ENV_FILE = find_dotenv(usecwd=True)
load_dotenv(ENV_FILE, override=True)

# Which model each kind of task uses (lesson 2.1: pick by task, not "the best one").
MODELS = {
    # Cheap, high-volume work: scoring hundreds of leads, classifying replies.
    "fast": os.getenv("MODEL_FAST", "gpt-4o-mini"),
    # Writing quality matters: company analysis, personalized emails.
    "smart": os.getenv("MODEL_SMART", "gpt-4o-mini"),
    # Multi-step thinking: deriving customer segments (lesson 2.6, used in step 2).
    "reasoning": os.getenv("MODEL_REASONING", "gpt-4o-mini"),
}

# Where requests go. Empty = OpenAI itself (https://api.openai.com/v1).
# For Azure OpenAI set it to https://YOUR-RESOURCE.openai.azure.com/openai/v1/
# and put your Azure key in OPENAI_API_KEY. On Azure, every model name in
# MODELS above must be your *deployment name*, not the model id.
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None

# Some built-in tools (e.g. web_search, lesson 4.3) exist on OpenAI but not on
# Azure OpenAI. Agents check this before offering them.
IS_AZURE = bool(OPENAI_BASE_URL and "azure" in OPENAI_BASE_URL.lower())

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "4"))

# Every API call is appended here as one JSON line (see core/client.py).
LOG_FILE = os.getenv("LOG_FILE", "logs/calls.jsonl")


def model_for(task: str) -> str:
    """Return the model name for a task kind: 'fast', 'smart' or 'reasoning'."""
    if task not in MODELS:
        raise ValueError(f"Unknown task kind {task!r}. Use one of: {', '.join(MODELS)}")
    return MODELS[task]
