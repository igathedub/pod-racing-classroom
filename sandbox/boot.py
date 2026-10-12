"""Container-only bootstrap: one source JSON line, then ordinary game stdin.

This is not a Python-language sandbox. The security boundary is the restricted
Docker container. Never invoke this bootstrap with student code on the host.
"""
import json
import sys


def main():
    # JSON escaping makes the physical line bounded even for 32 KiB Unicode.
    line = sys.stdin.readline(200000)
    if not line.endswith("\n"):
        raise ValueError("Missing or oversized source envelope")
    envelope = json.loads(line)
    source = envelope.get("code")
    if not isinstance(source, str) or len(source.encode("utf-8")) > 32768:
        raise ValueError("Source must be text of at most 32 KiB")
    compiled = compile(source, "student.py", "exec")
    print("__POD_CLASSROOM_READY__", flush=True)
    namespace = {"__name__": "__main__", "__file__": "/tmp/student.py"}
    exec(compiled, namespace, namespace)


if __name__ == "__main__":
    main()
