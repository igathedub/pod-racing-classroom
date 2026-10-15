"""Cautious: slower near checkpoints and when facing away from them."""
while True:
    try:
        x, y, cx, cy, distance, angle = map(int, input().split())
    except EOFError:
        break
    thrust = 80
    if distance < 1800:
        thrust = 40
    if abs(angle) > 45:
        thrust = 20
    if abs(angle) > 90:
        thrust = 0
    print(cx, cy, thrust, flush=True)