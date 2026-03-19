"""
test_mission_controller_minimal.py - Minimal sync test
"""

print("Starting import test...")

try:
    print("1. Importing ChatOpenAI...")
    from langchain_openai import ChatOpenAI
    print("   OK")
    
    print("2. Importing MissionController...")
    from orchestrator.mission_controller import MissionController
    print("   OK")
    
    print("3. Creating controller with default model...")
    controller = MissionController()
    print("   OK")
    
    print("4. Checking model config...")
    print(f"   Model name: {controller.model_config['name']}")
    print(f"   Model ID: {controller.model_config['model_id']}")
    
    print("\nAll imports successful!")
    
except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
