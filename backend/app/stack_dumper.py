import threading
import traceback
import sys
import time

def dump_stacks():
    while True:
        time.sleep(10)
        with open("stack_dump.txt", "a") as f:
            f.write("\n--- STACK DUMP ---\n")
            for th_id, frame in sys._current_frames().items():
                f.write(f"\nThread {th_id}:\n")
                traceback.print_stack(frame, file=f)
            f.flush()

t = threading.Thread(target=dump_stacks, daemon=True)
t.start()
