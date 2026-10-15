"""Cornering: smooth cosine throttle based on the relative angle."""
import math

while True:
    try:
        x, y, cx, cy, distance, angle = map(int, input().split())
    except EOFError:
        break
    alignment = max(0.0, math.cos(math.radians(angle)))
    thrust = round(100 * alignment * alignment)
    if distance < 1600:
        thrust = min(thrust, 50)
    print(cx, cy, thrust, flush=True)