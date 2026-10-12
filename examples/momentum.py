"""Momentum: estimate velocity from prior positions and counter drift."""
previous = None
boost_available = True
while True:
    try:
        x, y, cx, cy, distance, angle = map(int, input().split())
        ox, oy = map(int, input().split())
    except EOFError:
        break
    vx = 0 if previous is None else x - previous[0]
    vy = 0 if previous is None else y - previous[1]
    previous = (x, y)
    target_x, target_y = cx - 3 * vx, cy - 3 * vy
    thrust = 100 if abs(angle) < 60 else 25
    if boost_available and distance > 6500 and abs(angle) < 3:
        thrust = "BOOST"
        boost_available = False
    print(target_x, target_y, thrust, flush=True)
