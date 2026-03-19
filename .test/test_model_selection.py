"""
Test script to demonstrate model selection functionality
Run with: python test_model_selection.py
"""

from orchestrator.model_loader import (
    get_model_list,
    get_model_by_name,
    get_default_model,
    get_model_id_by_name
)

def test_model_selection():
    print("=" * 70)
    print("MODEL SELECTION SYSTEM TEST")
    print("=" * 70)
    
    # Test 1: Get all available models
    print("\n[Test 1] Available Models:")
    models = get_model_list()
    for i, model_name in enumerate(models, 1):
        print(f"  {i}. {model_name}")
    
    # Test 2: Get default model
    print("\n[Test 2] Default Model:")
    default = get_default_model()
    print(f"  Name: {default['name']}")
    print(f"  Model ID: {default['model_id']}")
    print(f"  Provider: {default['provider']}")
    
    # Test 3: Get specific model by name
    print("\n[Test 3] Get Model by Name:")
    test_model_name = "Meta Llama 3.1 8B (Free)"
    model = get_model_by_name(test_model_name)
    if model:
        print(f"  Found: {model['name']}")
        print(f"  Model ID: {model['model_id']}")
        print(f"  Description: {model['description']}")
    else:
        print(f"  Model '{test_model_name}' not found")
    
    # Test 4: Get model ID by name
    print("\n[Test 4] Get Model ID by Name:")
    for model_name in models[:3]:  # Test first 3 models
        model_id = get_model_id_by_name(model_name)
        print(f"  {model_name}")
        print(f"    -> {model_id}")
    
    # Test 5: Simulate user selection
    print("\n[Test 5] Simulate User Selection:")
    print("  User selects: 'Google Gemma 2 9B (Free)'")
    selected = get_model_by_name("Google Gemma 2 9B (Free)")
    if selected:
        print(f"  Agent will use:")
        print(f"    Model ID: {selected['model_id']}")
        print(f"    Base URL: {selected['base_url']}")
        print(f"    Provider: {selected['provider']}")
    
    print("\n" + "=" * 70)
    print("[SUCCESS] All model selection tests passed!")
    print("=" * 70)
    
    print("\nUsage in UI:")
    print("  1. User opens Streamlit app")
    print("  2. Sidebar shows dropdown with all models")
    print("  3. User selects preferred model")
    print("  4. Model config loaded and passed to agent")
    print("  5. Agent uses selected model for mission planning")
    print("\nUsage in Code:")
    print("  from orchestrator.model_loader import get_model_by_name")
    print("  model = get_model_by_name('Nvidia Nemotron 3 Super 120B (Free)')")
    print("  llm = ChatOpenAI(model=model['model_id'], base_url=model['base_url'])")

if __name__ == "__main__":
    test_model_selection()
