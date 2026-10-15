"""Sprinter: distance-based braking and reserved straight-line BOOST."""
boost_available = True
while True:
    try:
        x, y, cx, cy, distance, angle = map(int, input().split())
    except EOFError:
        break
    thrust = 100
    if distance < 2300:
        thrust = 65
    if distance < 1100:
        thrust = 20
    if abs(angle) > 70:
        thrust = 0
    if boost_available and distance > 7500 and abs(angle) < 2:
        thrust = "BOOST"
        boost_available = False
    print(cx, cy, thrust, flush=True)
