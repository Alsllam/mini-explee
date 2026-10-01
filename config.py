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

# How hard a reasoning model thinks before answering (lesson 2.6):
# low | medium | high. Leave EMPTY if MODEL_REASONING is not a reasoning model
# (e.g. gpt-4o-mini), because other models reject the "reasoning" parameter.
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "medium").strip() or None

# Batch API (lesson 4.4). On Azure a batch needs its OWN deployment of type
# "Global Batch" (or "Data Zone Batch"); a Standard deployment is refused.
# On OpenAI you can leave it empty: the "fast" model is used.
MODEL_BATCH = os.getenv("MODEL_BATCH", "").strip() or None

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "4"))

# Every API call is appended here as one JSON line (see core/client.py).
LOG_FILE = os.getenv("LOG_FILE", "logs/calls.jsonl")


def looks_like_secret(value: str | None) -> bool:
    """True if a value meant to be a model/deployment NAME looks like a key.

    Deployment names are short and readable ("gpt-4o-mini-batch"). Keys are long
    random strings. A key pasted into MODEL_* would be printed on screen, logged,
    and written into batch files - so we refuse it before any of that happens.
    """
    if not value:
        return False
    secrets = {os.getenv("OPENAI_API_KEY") or "", os.getenv("TAVILY_API_KEY") or ""} - {""}
    if value in secrets or value.startswith(("sk-", "tvly-")):
        return True
    return len(value) >= 32 and value.isalnum()  # long, no hyphens: not a typical name


def checked_name(env_var: str, value: str) -> str:
    """Return value, or stop with a message that never shows the value itself."""
    if looks_like_secret(value):
        raise ValueError(
            f"{env_var} in .env looks like an API KEY, not a model/deployment name. "
            "The value is hidden here on purpose. Put the deployment NAME there "
            "(e.g. gpt-4o-mini-batch). If a key was shown or shared anywhere, "
            "regenerate it in the Azure portal (Keys and Endpoint)."
        )
    return value


def model_for(task: str) -> str:
    """Return the model name for a task kind: 'fast', 'smart' or 'reasoning'."""
    if task not in MODELS:
        raise ValueError(f"Unknown task kind {task!r}. Use one of: {', '.join(MODELS)}")
    return checked_name(f"MODEL_{task.upper()}", MODELS[task])
