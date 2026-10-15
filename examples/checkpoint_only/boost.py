"""Straight-line boost: full throttle with one well-aligned long boost."""
boost_available = True
while True:
    try:
        x, y, cx, cy, distance, angle = map(int, input().split())
    except EOFError:
        break
    thrust = 100 if abs(angle) < 80 else 0
    if boost_available and distance > 6000 and abs(angle) < 4:
        thrust = "BOOST"
        boost_available = False
    print(cx, cy, thrust, flush=True)