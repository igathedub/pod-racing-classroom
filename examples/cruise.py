"""Cruise: a constant moderate throttle, without BOOST."""
while True:
    try:
        x, y, cx, cy, distance, angle = map(int, input().split())
        ox, oy = map(int, input().split())
    except EOFError:
        break
    print(cx, cy, 60, flush=True)
