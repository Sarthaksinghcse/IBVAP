import time
import math
from ai_engine.intelligence.behaviour_engine import BehaviourEngine, BehaviourLabel

def test_manual():
    print("=== IBVAP Module 1 (Behaviour Engine) Manual Test ===")
    
    engine = BehaviourEngine()
    
    # Test 1: Normal Transit (straight line, moderate speed)
    print("\n--- Test 1: Normal Transit ---")
    track_id = 1
    # Move from (10,10) to (50,50) over a few seconds
    for i in range(25):
        x = 10 + i * 2
        y = 10 + i * 2
        engine.update(track_id, x, y, timestamp=time.time() + i*0.5)
        
    label, weight = engine.classify(track_id)
    print(f"Result: {label.value} (Confidence weight: {weight:.2f})")
    
    
    # Test 2: Running (high velocity)
    print("\n--- Test 2: Running ---")
    track_id = 2
    # Move long distance in short time
    for i in range(25):
        x = 10 + i * 10
        y = 10 + i * 10
        # Time diff is very small (0.1s)
        engine.update(track_id, x, y, timestamp=time.time() + i*0.1)
        
    label, weight = engine.classify(track_id)
    print(f"Result: {label.value} (Confidence weight: {weight:.2f})")
    
    
    # Test 3: Circling (high tortuosity)
    print("\n--- Test 3: Circling ---")
    track_id = 3
    # Move in a circle
    radius = 20
    center_x, center_y = 50, 50
    for i in range(25):
        angle = i * (math.pi / 4) # 45 degrees
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        engine.update(track_id, x, y, timestamp=time.time() + i*0.5)
        
    label, weight = engine.classify(track_id)
    print(f"Result: {label.value} (Confidence weight: {weight:.2f})")
    
    
    # Test 4: Pacing (back and forth in a small area)
    print("\n--- Test 4: Pacing ---")
    track_id = 4
    # Move back and forth between x=20 and x=40
    for i in range(28):
        x = 20 if (i//5) % 2 == 0 else 40
        y = 30 # y stays roughly the same
        engine.update(track_id, x, y, timestamp=time.time() + i*0.5)
        
    label, weight = engine.classify(track_id)
    print(f"Result: {label.value} (Confidence weight: {weight:.2f})")

if __name__ == "__main__":
    test_manual()
