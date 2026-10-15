"""Edit this bot and submit it with your alias on the classroom website.

Each turn stdin gives ONE line:
  x y checkpoint_x checkpoint_y distance relative_angle
Print ONE line: target_x target_y thrust (integer 0..100 or BOOST).
BOOST gives 650 once per race. Aim at checkpoints in the given order.
Use print(..., flush=True). Never print debugging to stdout.
There are no course/lap bootstrap inputs. Standard-library imports are allowed.
"""

while True:
    try:
        x, y, checkpoint_x, checkpoint_y, distance, angle = map(int, input().split())
    except EOFError:
        break

    # Start here: try braking for corners or remembering previous positions.
    thrust = 100
    if abs(angle) > 90:
        thrust = 0
    print(checkpoint_x, checkpoint_y, thrust, flush=True)
