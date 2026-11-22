import argparse
import json
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--pid", type=int)
mode = parser.parse_args().pid
if mode == 1:
    print(json.dumps({"ok": False, "error": {"message": "Sign in to Antigravity"}}))
elif mode == 2:
    print("invalid json")
elif mode == 3:
    sys.exit(1)
elif mode == 4:
    time.sleep(60)
elif mode == 5:
    print(json.dumps({"ok": True, "buckets": [{"remaining": 2}]}))
else:
    print(json.dumps({"ok": True, "buckets": [
        {"id": "test", "name": "Test", "group": "Premium", "remaining": 0},
    ]}))
