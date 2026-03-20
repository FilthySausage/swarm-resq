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

def add_custom_model(new_model: Dict) -> bool:
    """
    Add a custom model to config/models.json and save it
    """
    try:
        if not MODELS_FILE.exists():
            return False
            
        with open(MODELS_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        # Optional: check if exists to avoid duplicates by name
        for existing in config.get("models", []):
            if existing.get("name") == new_model.get("name"):
                # Update existing
                existing.update(new_model)
                break
        else:
            config["models"].append(new_model)
            
        with open(MODELS_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving custom model: {e}")
        return False


def remove_custom_model(model_name: str) -> bool:
    """
    Remove a custom model by display name from config/models.json.
    Refuses to remove non-custom models.
    """
    try:
        if not MODELS_FILE.exists():
            return False

        with open(MODELS_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

        models = config.get("models", [])
        kept = []
        removed = False
        for model in models:
            name = str(model.get("name", "")).strip()
            desc = str(model.get("description", "")).strip().lower()
            is_custom = name.endswith("(Custom)") or desc == "custom user-added model"
            if name == model_name and is_custom:
                removed = True
                continue
            kept.append(model)

        if not removed:
            return False

        config["models"] = kept

        # Ensure default model remains valid after deletion.
        default_id = config.get("default_model")
        ids = {str(m.get("model_id", "")) for m in kept}
        if default_id not in ids and kept:
            config["default_model"] = kept[0].get("model_id")

        with open(MODELS_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error removing custom model: {e}")
        return False

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
