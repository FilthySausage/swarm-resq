"""
Test Single-Prompt Mission System
Run with: python test_single_prompt.py

Prerequisites:
1. Start MCP server: uvicorn mcp_server.server:app --reload --port 8000
2. Set OPENROUTER_API_KEY in .env
3. Run this test
"""

import asyncio
from orchestrator.mission_controller import MissionController

async def test_single_prompt_mission():
    print("=" * 70)
    print("TESTING SINGLE-PROMPT MISSION SYSTEM")
    print("=" * 70)
    
    # Create mission controller
    controller = MissionController(model_name="Nvidia Nemotron 3 Super 120B (Free)")
    
    # Run full mission
    print("\nStarting mission...")
    print("This will:")
    print("  1. Get current state from MCP server")
    print("  2. Send single prompt to AI")
    print("  3. AI returns JSON plan")
    print("  4. Execute plan autonomously")
    print("  5. Monitor for battery issues")
    print("  6. Repeat until all survivors found")
    print("\n" + "=" * 70)
    
    try:
        result = await controller.run_full_mission(
            briefing="Find all survivor coordinates using systematic search"
        )
        
        if result.get("success"):
            print("\n" + "=" * 70)
            print("✅ MISSION TEST PASSED")
            print("=" * 70)
            print(f"Turns: {result['turns']}")
            print(f"Survivors found: {len(result['survivors_found'])}")
            
            if result['survivors_found']:
                print("\nSurvivor Coordinates:")
                for i, coord in enumerate(result['survivors_found'], 1):
                    print(f"  {i}. ({coord['x']}, {coord['y']})")
        else:
            print("\n✗ Mission failed")
            
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_single_prompt_mission())
