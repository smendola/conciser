"""Persistent storage for OpenAI Responses API chain IDs.

Chains are pre-initialized conversations (one per aggressiveness level 1-10)
that already contain the system prompt (levels 1+2). Each job then continues
from the tip of the appropriate chain, sending only the user prompt (level 3).

The chains file (condenser_chains.json) is stored at the project root alongside
.env. It is regenerated automatically when prompts change or the model changes.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional, Dict

from ..config import PROJECT_ROOT

logger = logging.getLogger(__name__)

CHAINS_FILE = PROJECT_ROOT / "condenser_chains.json"


def compute_prompt_hash() -> str:
    """Hash all 10 system prompts (levels 1+2) to detect stale chains."""
    from .prompt_templates import CONDENSE_SYSTEM_PROMPT, STRATEGY_PROMPTS, RETENTION_RANGES

    parts = [CONDENSE_SYSTEM_PROMPT]
    for level in range(1, 11):
        retention_range = RETENTION_RANGES[level]
        parts.append(STRATEGY_PROMPTS[level].format(retention_range=retention_range))
    return hashlib.sha256("".join(parts).encode()).hexdigest()[:16]


def load_chains(model: str) -> Optional[Dict[str, str]]:
    """
    Load chain IDs from file if valid for the current prompts and model.
    Returns None if file is missing, prompts have changed, or model differs.
    """
    if not CHAINS_FILE.exists():
        return None
    try:
        data = json.loads(CHAINS_FILE.read_text())
        if data.get("prompt_hash") != compute_prompt_hash():
            logger.warning("Condenser chain IDs are stale (prompts changed) — will re-init")
            return None
        if data.get("model") != model:
            logger.warning(
                f"Condenser chains were built for model '{data.get('model')}', "
                f"current model is '{model}' — will re-init"
            )
            return None
        return data["chains"]
    except Exception as e:
        logger.warning(f"Failed to load condenser chains: {e}")
        return None


def save_chains(model: str, chains: Dict[str, str]) -> None:
    """Save chain IDs alongside a prompt hash and model name."""
    data = {
        "prompt_hash": compute_prompt_hash(),
        "model": model,
        "chains": chains,
    }
    CHAINS_FILE.write_text(json.dumps(data, indent=2))
    logger.info(f"Saved condenser chains to {CHAINS_FILE}")
