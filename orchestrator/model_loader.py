"""
model_loader.py - Load and manage AI model configurations
Reads from config/models.json and provides model selection utilities
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

# Path to models configuration
CONFIG_DIR = Path(__file__).parent.parent / "config"
MODELS_FILE = CONFIG_DIR / "models.json"


def _normalize_base_url(url: str) -> str:
    """Normalize OpenAI-compatible base URL; append /v1 when missing."""
    cleaned = (url or "").rstrip("/")
    if cleaned.endswith("/v1"):
        return cleaned
    return f"{cleaned}/v1"


def _apply_env_overrides(config: Dict) -> Dict:
    """Apply environment overrides without changing model IDs or names."""
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "").strip()
    if not ollama_base_url:
        return config

    models = config.get("models", [])
    for model in models:
        provider = str(model.get("provider", "")).strip().lower()
        if provider == "ollama":
            model["base_url"] = _normalize_base_url(ollama_base_url)

    return config


def load_models() -> Dict:
    """
    Load model configurations from config/models.json
    
    Returns:
        Dict with 'models' list and 'default_model' string
    """
    try:
        if not MODELS_FILE.exists():
            raise FileNotFoundError(f"Models config not found: {MODELS_FILE}")
        
        with open(MODELS_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

        config = _apply_env_overrides(config)
        return config
    except Exception as e:
        print(f"Error loading models config: {e}")
        # Return fallback configuration
        return {
            "models": [
                {
                    "name": "Ollama Llama2 (Local)",
                    "provider": "Ollama",
                    "model_id": "llama2",
                    "base_url": "http://localhost:11434/v1",
                    "requires_key": False,
                    "description": "Default fallback model"
                }
            ],
            "default_model": "llama2"
        }


def get_model_list() -> List[str]:
    """
    Get list of model names for UI dropdown
    
    Returns:
        List of model display names
    """
    config = load_models()
    return [model["name"] for model in config["models"]]


def get_model_by_name(name: str) -> Optional[Dict]:
    """
    Get model configuration by display name
    
    Args:
        name: Display name of the model
        
    Returns:
        Model configuration dict or None if not found
    """
    config = load_models()
    for model in config["models"]:
        if model["name"] == name:
            return model
    return None


def get_default_model() -> Dict:
    """
    Get the default model configuration
    
    Returns:
        Default model configuration dict
    """
    config = load_models()
    default_id = config.get("default_model")
    
    # Find model with matching ID
    for model in config["models"]:
        if model["model_id"] == default_id:
            return model
    
    # Fallback to first model
    return config["models"][0]


def get_model_id_by_name(name: str) -> str:
    """
    Get model ID from display name
    
    Args:
        name: Display name of the model
        
    Returns:
        Model ID string (e.g., "nvidia/nemotron-3-super-120b-a12b:free")
    """
    model = get_model_by_name(name)
    if model:
        return model["model_id"]
    
    # Fallback to default
    return get_default_model()["model_id"]


if __name__ == "__main__":
    # Test the loader
    print("Available Models:")
    print("=" * 60)
    for name in get_model_list():
        model = get_model_by_name(name)
        print(f"\n{name}")
        print(f"  Provider: {model['provider']}")
        print(f"  Model ID: {model['model_id']}")
        print(f"  Description: {model['description']}")
    
    print("\n" + "=" * 60)
    print(f"Default Model: {get_default_model()['name']}")
