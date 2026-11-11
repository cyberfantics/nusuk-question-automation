#!/usr/bin/env python3
"""Nusuk Challenge auto-answer bot.

Drives the Nusuk Android app over adb:
  * reads the screen with `uiautomator dump` (no OCR needed - Compose exposes text)
  * looks the question up in a local answer bank (questions repeat)
  * taps the right option, then "Check your answer"
  * handles "Open the door?" dialogs and door selection

Usage:
  python nusuk.py state              # print what is on screen
  python nusuk.py run -n 5           # answer up to 5 questions
  python nusuk.py run -n 5 --door any
  python nusuk.py learn "Q?" "answer"
  python nusuk.py learn              # no typing: read the question off the
                                     # screen, tap the answer, it saves it
  python nusuk.py stats

Exit codes: 0 ok / done, 3 unknown question (needs learning), 4 could not act.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
from difflib import SequenceMatcher

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---- developer banner (colorama, optional) ------------------------------
# Same style as nusuk-key-automation: colorama gives the banner and the
# key lines their colours on Windows. If it is not installed everything
# still prints, just without colours.
try:
    from colorama import init as _colorama_init, Fore, Style
    _colorama_init(autoreset=True)
    _COLOR = True
except ImportError:
    _COLOR = False

    class _NoColor:
        def __getattr__(self, name):
            return ""

    Fore = Style = _NoColor()


def _paint(text, color=""):
    return f"{color}{text}" if _COLOR else text


def _set_console_title():
    """Put the tool name in the console window's title bar (Windows only).

    The title bar is the one part of a console window that never scrolls
    away, so the tool stays identified no matter how many questions run.
    """
    if os.name != "nt":
        return
    try:
        os.system("title NUSUK QUESTION AUTOMATION - by Mansoor Bukhari - CyberFantics")
    except Exception:
        pass


def print_banner():
    """Show the tool title and the developer's links, in colour when possible."""
    _set_console_title()
    bar = "=" * 55
    print(_paint(bar, Fore.CYAN + Style.BRIGHT))
    print(_paint("  NUSUK QUESTION AUTOMATION", Fore.CYAN + Style.BRIGHT))
    print(_paint("  by Mansoor Bukhari  •  CyberFantics", Fore.GREEN + Style.BRIGHT))
    print(_paint("  Python & Flutter Developer | AI Automation Engineer", Fore.YELLOW))
    print(_paint("-" * 55, Fore.CYAN))
    print(_paint("  GitHub:    ", Fore.YELLOW) + _paint("github.com/cyberfantics", Fore.WHITE + Style.BRIGHT))
    print(_paint("  LinkedIn:  ", Fore.YELLOW) + _paint("linkedin.com/in/mansoor-bukhari", Fore.WHITE + Style.BRIGHT))
    print(_paint("  Instagram: ", Fore.YELLOW) + _paint("instagram.com/CyberFantics", Fore.WHITE + Style.BRIGHT))
    print(_paint("  YouTube:   ", Fore.YELLOW) + _paint("youtube.com/@CyberFantics", Fore.WHITE + Style.BRIGHT))
    print(_paint(bar, Fore.CYAN + Style.BRIGHT))


HERE = os.path.dirname(os.path.abspath(__file__))
BANK_PATH = os.path.join(HERE, "qa_bank.json")
DOORS = ["prophet", "quran", "makkah", "madinah"]
DOOR_NAMES = {
    "prophet": "The Prophet’s",
    "quran": "The Quran",
    "makkah": "Makkah and the",
    "madinah": "Madinah and the",
}
CHECK_BUTTON_FALLBACKS = [1464, 1460, 1470, 1522]
OPTION_SETTLE = 0.12
CHECK_SETTLE = 0.12


# ---------------------------------------------------------------- adb helpers
def adb(*args: str, timeout: int = 30) -> str:
    """Run adb and return stdout. Empty string if adb is missing or fails,
    so the tool fails cleanly (no question on screen) instead of crashing."""
    try:
        out = subprocess.run(
            ["adb", *args], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return out.stdout


def tap(x: int, y: int, settle: float = 0.08) -> None:
    adb("shell", "input", "tap", str(int(x)), str(int(y)))
    time.sleep(settle)


def dump() -> list[dict]:
    """Return screen nodes: {text, clickable, bounds(x1,y1,x2,y2), cls}."""
    xml = ""
    for _ in range(3):
        xml = adb("exec-out", "uiautomator", "dump", "/dev/tty")
        if "<hierarchy" in xml:
            break
        time.sleep(0.7)
    nodes = []
    for m in re.finditer(r"<node ([^>]*?)/?>", xml):
        a = m.group(1)

        def attr(key: str) -> str:
            mm = re.search(key + r'="([^"]*)"', a)
            return mm.group(1) if mm else ""

        b = re.search(r"bounds=\"\[(\d+),(\d+)\]\[(\d+),(\d+)\]\"", a)
        if not b:
            continue
        text = (attr("text") or attr("content-desc")).strip()
        text = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", text).strip()
        nodes.append({
            "text": text,
            "clickable": attr("clickable") == "true",
            "selected": attr("selected") == "true",
            "checked": attr("checked") == "true",
            "cls": attr("class").split(".")[-1],
            "bounds": tuple(int(v) for v in b.groups()),
        })
    return nodes


def center(bounds) -> tuple[int, int]:
    x1, y1, x2, y2 = bounds
    return (x1 + x2) // 2, (y1 + y2) // 2


def sig(nodes: list[dict]) -> tuple:
    return tuple(n["text"] for n in nodes if n["text"])


def wait_change(prev: tuple, timeout: float = 15.0) -> dict:
    """Poll until the on-screen text differs from `prev`.

    Replaces fixed sleeps: the loop advances the moment the app reacts, and
    still tolerates a slow render by waiting up to `timeout` seconds.
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        scr = read_screen()
        if sig(scr["nodes"]) != prev:
            return scr
    return read_screen()


# ------------------------------------------------------------------ screen read
def read_screen() -> dict:
    nodes = dump()
    texts = [n["text"] for n in nodes if n["text"]]
    joined = " | ".join(texts)
    if "Choose a door" in joined:
        return {"kind": "chooser", "nodes": nodes}
    if "Do you want to use your key" in joined:
        return {"kind": "key_dialog", "nodes": nodes}
    if "Something went wrong" in joined or "Something Went Wrong" in joined:
        return {"kind": "error_dialog", "nodes": nodes}
    # The check button label is sometimes clipped away entirely, so also treat
    # the "key can unlock the door" footer as proof we are on a question card.
    has_check = "Check your answer" in joined or "Your key can unlock the door" in joined
    result_hit = re.search(r"\b(Correct|Wrong|Incorrect|Not quite)\b", joined, re.I)
    if has_check and not result_hit:
        return {"kind": "question", **parse_question(nodes)}
    if result_hit or "Play again" in joined or "in the draw" in joined:
        return {"kind": "result", "nodes": nodes,
                "correct": bool(re.search(r"\bCorrect\b", joined, re.I))}
    return {"kind": "unknown", "nodes": nodes, "texts": texts}


def parse_question(nodes: list[dict]) -> dict:
    clue = "Your key can unlock the door"
    qnode = None
    for n in nodes:
        t = n["text"]
        if not t or t == "Check your answer" or clue in t:
            continue
        if len(t) > 15 and (t.endswith("?") or len(t) > 25):
            qnode = n
            break
    options = []
    if qnode:
        for n in nodes:
            t = n["text"]
            if not t or t == qnode["text"] or clue in t or t == "Check your answer":
                continue
            if n["bounds"][1] > qnode["bounds"][3] - 5:
                if len(t) <= 120:
                    options.append(n)
    # de-duplicate by text while keeping order
    seen, uniq = set(), []
    for o in options:
        if o["text"] not in seen:
            seen.add(o["text"])
            uniq.append(o)
    clickables = [n for n in nodes if n["clickable"]]
    for o in uniq:
        cx, cy = center(o["bounds"])
        row = next((c for c in clickables if c["bounds"] != o["bounds"]
                    and c["bounds"][0] <= cx <= c["bounds"][2]
                    and c["bounds"][1] <= cy <= c["bounds"][3]), None)
        o["tap"] = center(row["bounds"]) if row else (cx, cy)
    return {"question": qnode["text"] if qnode else "", "options": uniq[:6], "nodes": nodes}


# ------------------------------------------------------------------- the bank
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("’", "'").replace("`", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"[^a-z0-9' ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def load_bank() -> dict:
    if os.path.exists(BANK_PATH):
        with open(BANK_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_bank(bank: dict) -> None:
    with open(BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(bank, f, indent=2, ensure_ascii=False, sort_keys=True)


def lookup(bank: dict, question: str):
    key = norm(question)
    if not key:
        return None
    hit = bank.get(key)
    if hit:
        return hit, 1.0
    # Words that flip the meaning of an otherwise near-identical question
    # ("first" vs "last", "not", ...) must never be fuzzy-matched away.
    FLIP = {"first", "last", "not", "except", "before", "after", "longest", "shortest"}
    kw = set(key.split())

    best, score = None, 0.0
    for k, v in bank.items():
        if (kw & FLIP) != (set(k.split()) & FLIP):
            continue
        r = SequenceMatcher(None, key, k).ratio()
        if r > score:
            best, score = v, r
    if best and score >= 0.95:
        return best, score
    return None


def pick_option(options: list[dict], answer: str):
    target = norm(answer)
    for o in options:
        if norm(o["text"]) == target:
            return o
    for o in options:
        t = norm(o["text"])
        if target and (target in t or t in target):
            return o
    best, score = None, 0.0
    for o in options:
        r = SequenceMatcher(None, target, norm(o["text"])).ratio()
        if r > score:
            best, score = o, r
    return best if score >= 0.6 else None


# --------------------------------------------------------------------- actions
def do_open_door(screen: dict, door: str | None) -> bool:
    nodes = screen["nodes"]
    if door:
        want = DOOR_NAMES.get(door, "")
        cards = [n for n in nodes if n["clickable"] and n["bounds"][3] - n["bounds"][1] > 300]
        labels = {n["text"]: n["bounds"] for n in nodes if n["text"] in DOOR_NAMES.values()}
        for name, lb in labels.items():
            if name == want:
                # card sits above its label
                target = min(cards, key=lambda c: abs(center(c["bounds"])[0] - center(lb)[0])
                             + abs(c["bounds"][3] - lb[1]), default=None)
                if target:
                    tap(*center(target["bounds"]), settle=0.08)
                    return True
    cards = [n for n in nodes if n["clickable"] and n["bounds"][3] - n["bounds"][1] > 300]
    if not cards:
        return False
    tap(*center(random.choice(cards)["bounds"]), settle=0.08)
    return True


def answer_question(screen: dict, bank: dict) -> str:
    q, options = screen["question"], screen["options"]
    if not q or len(options) < 2:
        print(_paint("!! could not parse question/options", Fore.RED))
        for o in options:
            print("   opt:", o["text"])
        return "parse_fail"
    hit = lookup(bank, q)
    if not hit:
        print(_paint("\n=== UNKNOWN QUESTION ===", Fore.YELLOW + Style.BRIGHT))
        print(q)
        for i, o in enumerate(options, 1):
            print(f"  {i}. {o['text']}")
        print("=== add with: python nusuk.py learn \"<question>\" \"<answer>\" ===")
        print("=== or just:    python nusuk.py learn   (tap the answer on your phone) ===\n")
        return "unknown"
    entry, score = hit
    opt = pick_option(options, entry["answer"])
    if not opt:
        print(_paint(f"!! answer '{entry['answer']}' does not match options for: {q}", Fore.RED))
        for i, o in enumerate(options, 1):
            print(f"  {i}. {o['text']}")
        return "unknown"
    print(_paint(f"Q: {q}", Fore.CYAN) + "\n   -> " + _paint(opt["text"], Fore.GREEN + Style.BRIGHT) + _paint(f"  (bank score {score:.2f})", Fore.YELLOW), flush=True)
    tap(*opt.get("tap", center(opt["bounds"])), settle=OPTION_SETTLE)
    tap_check(screen)
    screen["chosen"] = opt["text"]
    screen["chosen_bounds"] = opt.get("tap", center(opt["bounds"]))
    return "answered"


def recover() -> None:
    """A stray tap can land in another app (notification, share sheet).
    Press back twice and bring Nusuk to the foreground again."""
    adb("shell", "cmd", "statusbar", "collapse")
    for _ in range(2):
        adb("shell", "input", "keyevent", "4")
        time.sleep(0.4)
    adb("shell", "monkey", "-p", "com.moh.nusukapp", "-c",
        "android.intent.category.LAUNCHER", "1")
    time.sleep(2.0)


def ensure_check_visible(screen: dict) -> dict:
    """The 'Check your answer' pill sits at the very bottom edge and is often
    clipped below the fold (long questions push it off-screen). Scroll the
    question sheet up until the label has real bounds, then re-read."""
    for _ in range(3):
        label = [n for n in screen["nodes"] if "Check your answer" in n["text"]]
        if any(n["bounds"] != (0, 0, 0, 0) for n in label):
            return screen
        adb("shell", "input", "swipe", "360", "1150", "360", "850", "250")
        time.sleep(0.35)
        screen = read_screen()
        if screen["kind"] != "question":
            return screen
    return screen


def tap_check(screen: dict) -> None:
    """Tap 'Check your answer' only - the caller polls for the result.

    On this Compose screen the button label is clipped (bounds 0,0,0,0); the
    real tap target is a full-width clickable strip hugging the bottom edge.
    """
    cands = [n for n in screen["nodes"] if n["clickable"]
             and n["bounds"][1] >= 1400
             and n["bounds"][2] - n["bounds"][0] >= 400
             and n["bounds"][3] > 0]
    if cands:
        tap(*center(max(cands, key=lambda n: n["bounds"][1])["bounds"]), settle=CHECK_SETTLE)
    else:
        tap(360, 1464, settle=CHECK_SETTLE)


LOG_PATH = os.path.join(HERE, "answers.log")


def log_line(question: str, chosen: str, correct: bool) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{stamp}\t{'OK' if correct else 'WRONG'}\t{question}\t{chosen}\n")


def handle_result(screen: dict, bank: dict, q: str, chosen: str = "") -> None:
    """After checking the answer the per-question entry gets a hit counter."""
    if screen.get("correct"):
        print(_paint("   correct ✔", Fore.GREEN + Style.BRIGHT))
    else:
        print(_paint("   WRONG ✘ - bank entry needs fixing", Fore.RED + Style.BRIGHT))
        key = norm(q)
        if key in bank:
            bank[key]["verified"] = False
            save_bank(bank)
    log_line(q, chosen, bool(screen.get("correct")))


def say(msg: str) -> None:
    print(msg, flush=True)


def run(rounds: int, door: str | None, deadline: float | None = None) -> int:
    print_banner()
    bank = load_bank()
    answered = correct = 0
    i = 0
    guard = 0
    per_kind: dict[str, int] = {}
    scr = read_screen()
    while answered < rounds:
        guard += 1
        if guard > 80:
            say(_paint("!! watchdog: too many steps, stopping", Fore.RED))
            return 4
        if deadline and time.time() > deadline:
            say(_paint(f"!! time budget reached ({answered} answered)", Fore.YELLOW))
            return 0
        kind = scr["kind"]
        per_kind[kind] = per_kind.get(kind, 0) + 1
        if per_kind[kind] > 6:
            say(_paint(f"!! stuck on '{kind}' ({per_kind[kind]}x). Screen text:", Fore.RED))
            for n in scr["nodes"]:
                if n["text"]:
                    say(f"     {n['text'][:60]}")
            return 4
        prev = sig(scr["nodes"])
        if kind == "chooser":
            d = door if door and door != "any" else DOORS[i % len(DOORS)]
            i += 1
            say(_paint(f".. door: {d}", Fore.CYAN))
            if not do_open_door(scr, None if door == "any" else d):
                say(_paint("!! no door cards found", Fore.RED))
                return 4
            scr = wait_change(prev)
            per_kind.clear()
            continue
        if kind == "error_dialog":
            close = [n for n in scr["nodes"] if n["text"].strip() == "Close"]
            if close:
                tap(*center(close[0]["bounds"]), settle=0.08)
            scr = wait_change(prev)
            continue
        if kind == "key_dialog":
            ok = [n for n in scr["nodes"] if "Open the door" in n["text"]]
            if not ok:
                say(_paint("!! key dialog with no 'Open the door' button", Fore.RED))
                for n in scr["nodes"]:
                    if n["text"]:
                        say(f"     {n['text'][:60]}")
                return 4
            tap(*center(ok[0]["bounds"]), settle=0.08)
            scr = wait_change(prev)
            per_kind.clear()
            continue
        if kind == "question":
            scr = ensure_check_visible(scr)
            if scr["kind"] != "question":
                continue
            res = answer_question(scr, bank)
            if res == "unknown":
                say(_paint(f"stopped at unknown question #{answered + 1} of this run", Fore.YELLOW))
                return 3
            if res == "parse_fail":
                return 4
            last_q = scr["question"]
            after = scr
            for _ in range(3):
                after = wait_change(prev)
                if after["kind"] == "result":
                    break
                if after["kind"] == "question" and after["question"] == last_q:
                    say(_paint("   (answer did not submit, retrying option + check)", Fore.YELLOW))
                    tp = sig(after["nodes"])
                    if scr.get("chosen_bounds"):
                        tap(*scr["chosen_bounds"], settle=OPTION_SETTLE)
                    tap_check(after)
                    prev = tp
                    continue
                break
            if after is None or after.get("kind") != "result":
                scr = after if after else read_screen()
                continue
            handle_result(after, bank, last_q, scr.get("chosen", ""))
            if after.get("correct"):
                correct += 1
            answered += 1
            per_kind.clear()
            key = norm(last_q)
            if key in bank:
                bank[key]["used"] = bank[key].get("used", 0) + 1
                save_bank(bank)
            if answered < rounds:
                play = [n for n in after["nodes"] if "Play again" in n["text"]]
                if play:
                    pv = sig(after["nodes"])
                    tap(*center(play[0]["bounds"]), settle=0.08)
                    scr = wait_change(pv)
                else:
                    scr = read_screen()
            else:
                scr = after
            continue
        if kind == "result":
            play = [n for n in scr["nodes"] if "Play again" in n["text"]]
            if not play:
                say(_paint("on result screen, no 'Play again'", Fore.RED))
                return 4
            tap(*center(play[0]["bounds"]), settle=0.08)
            scr = wait_change(prev)
            continue
        joined = ", ".join(scr.get("texts", []))
        if "Your key can unlock the door" in joined or "Check your answer" in joined:
            scr = wait_change(prev, timeout=6)
            continue
        say(_paint(f"!! stray screen, recovering: {joined[:120]}", Fore.RED))
        recover()
        scr = read_screen()
        per_kind.clear()
        if scr["kind"] == "unknown":
            say(_paint("!! still lost after recovery", Fore.RED))
            return 4
    say(_paint("Done: answered %d, correct %d." % (answered, correct), Fore.GREEN + Style.BRIGHT))
    return 0


def learn(question: str, answer: str) -> int:
    bank = load_bank()
    key = norm(question)
    bank[key] = {"question": question, "answer": answer,
                 "used": bank.get(key, {}).get("used", 0)}
    save_bank(bank)
    print(_paint(f"learned ({len(bank)} total): {question} -> {answer}", Fore.GREEN + Style.BRIGHT))
    return 0


def wait_for_selection(timeout: float = 90.0):
    """Wait until the user taps an option on the phone.

    Polls the screen for a selected/checked option. Returns the tapped
    option node, or None if nothing was tapped before the timeout, or if
    the screen left the question card (e.g. the user tapped Check already).
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        scr = read_screen()
        if scr["kind"] != "question":
            return None
        for o in scr.get("options", []):
            if o.get("selected") or o.get("checked"):
                return o
        time.sleep(1.0)
    return None


def learn_interactive() -> int:
    """Learn the question on screen right now — no typing needed.

    Read the question off the phone, show its options, and wait for the
    user to tap the correct answer. The tapped option is saved into the
    bank, then the answer is checked in the app to confirm it.
    """
    print_banner()
    bank = load_bank()
    scr = read_screen()
    if scr["kind"] != "question":
        print(_paint("No question on screen. Open a question in the Nusuk app first, then run learn.", Fore.YELLOW))
        return 1
    q, options = scr["question"], scr["options"]
    if not q or len(options) < 2:
        print(_paint("Could not read the question or its options.", Fore.RED))
        return 1
    hit = lookup(bank, q)
    if hit:
        entry, score = hit
        print(_paint(f"Already in the bank: {q} -> {entry['answer']}  (score {score:.2f})", Fore.CYAN))
        return 0
    print(_paint(f"Question: {q}", Fore.CYAN + Style.BRIGHT))
    for i, o in enumerate(options, 1):
        print(f"  {i}. {o['text']}")
    print("Tap the correct answer on your phone — I'll watch for it (up to 90 seconds).")
    chosen = wait_for_selection()
    if chosen is None:
        # Could not see the tap (some screens don't mark the tapped option
        # as selected). Fall back to a number — still no typing the question.
        print(_paint("Could not see which option you tapped.", Fore.YELLOW))
        for _ in range(3):
            try:
                pick = input("Type the number of the answer you tapped (Enter to quit): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nQuitting without saving.")
                return 0
            if not pick:
                return 0
            if pick.isdigit() and 1 <= int(pick) <= len(options):
                chosen = options[int(pick) - 1]
                break
            print(f"Enter a number from 1 to {len(options)}.")
        if chosen is None:
            print("Quitting without saving.")
            return 0
    answer = chosen["text"]
    learn(q, answer)
    bank = load_bank()  # refresh: learn() saved a fresh copy with the new entry
    # Confirm it in the app: tap Check and read the result.
    scr = read_screen()
    if scr["kind"] == "result":
        handle_result(scr, bank, q, answer)
    elif scr["kind"] == "question":
        tap_check(scr)
        after = wait_change(sig(scr["nodes"]))
        if after and after["kind"] == "result":
            handle_result(after, bank, q, answer)
        else:
            print("Saved. Tap Check your answer in the app to confirm it.")
    else:
        print("Saved. Tap Check your answer in the app to confirm it.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Nusuk Challenge auto-answer bot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("state")
    p_run = sub.add_parser("run")
    p_run.add_argument("-n", "--rounds", type=int, default=5)
    p_run.add_argument("--door", default="any", choices=["any", *DOORS])
    p_run.add_argument("--max-seconds", type=float, default=0)
    p_learn = sub.add_parser("learn")
    p_learn.add_argument("question", nargs="?")
    p_learn.add_argument("answer", nargs="?")
    sub.add_parser("stats")
    a = ap.parse_args()

    if a.cmd == "state":
        s = read_screen()
        print("kind:", _paint(s["kind"], Fore.CYAN))
        if s["kind"] == "question":
            print("Q:", _paint(s["question"], Fore.CYAN))
            for i, o in enumerate(s["options"], 1):
                print(f"  {i}. {o['text']}")
        else:
            for n in s.get("nodes", []):
                if n["text"]:
                    print(f"  {n['text'][:70]}")
        return 0
    if a.cmd == "run":
        dl = time.time() + a.max_seconds if a.max_seconds else None
        return run(a.rounds, a.door, dl)
    if a.cmd == "learn":
        if a.question is None and a.answer is None:
            return learn_interactive()
        if a.question is None or a.answer is None:
            print(_paint('Usage: python nusuk.py learn "question" "answer"  (or just: python nusuk.py learn)', Fore.YELLOW))
            return 1
        return learn(a.question, a.answer)
    if a.cmd == "stats":
        bank = load_bank()
        print(_paint(f"{len(bank)} questions in bank", Fore.CYAN + Style.BRIGHT))
        for k, v in sorted(bank.items(), key=lambda kv: -kv[1].get("used", 0))[:20]:
            print(f"  [{v.get('used',0)}x] {v['question'][:70]} -> {v['answer'][:40]}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
