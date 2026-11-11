"""One-function entry point for the exe: answer all questions.

The exe built from this file does one thing — answer Nusuk Challenge
questions until it meets one it does not know (then it stops, and you
teach it with `python nusuk.py learn`), gets stuck, or runs out of steps.
It takes no arguments: double-click it and it goes.

For the other functions (learn, state, stats) run the script itself:

    python nusuk.py learn
    python nusuk.py learn "Question?" "Answer"
    python nusuk.py state
    python nusuk.py stats
"""
import argparse
import sys
import time

import nusuk


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Nusuk Question Automation — answer all questions")
    ap.add_argument("-n", "--rounds", type=int, default=1000,
                    help="how many questions to answer "
                         "(default: 1000, effectively all)")
    ap.add_argument("--door", default="any", choices=["any", *nusuk.DOORS],
                    help="which door to open (default: any, picked in turn)")
    ap.add_argument("--max-seconds", type=float, default=0,
                    help="stop after this many seconds (default: no limit)")
    a = ap.parse_args()
    deadline = time.time() + a.max_seconds if a.max_seconds else None
    # A run that answers everything needs far more screen steps than the
    # script's default watchdog (80); 2000 steps is roughly 600 questions.
    return nusuk.run(a.rounds, a.door, deadline, max_steps=2000)


if __name__ == "__main__":
    sys.exit(main())
