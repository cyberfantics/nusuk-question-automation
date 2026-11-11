# Nusuk Question Automation

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![Android](https://img.shields.io/badge/platform-Android-green)
![ADB](https://img.shields.io/badge/automation-ADB-lightgrey)

I got tired of answering the same Nusuk challenge questions by hand, so I wrote this. It connects to your Android phone over ADB, reads the question off the screen, looks it up in a local answer bank, and taps the right option for you. No root, no modded app, no OCR — the app shows its own text, so the script just reads it. It just taps the same buttons you would tap yourself.

Not affiliated with Nusuk in any way. Use it at your own risk, and if Nusuk changes their app screens one day, this will probably need a fix.

## How the challenge works

In the Nusuk app, the challenge is a quiz behind four doors — the Prophet, the Quran, Makkah, and Madinah. You spend a key to open a door, answer the question, and tap Check your answer. Right or wrong, it moves on to the next question — but a wrong answer marks that bank entry as not verified, so you can fix it instead of the tool confidently repeating it. The questions repeat — the same ones come around again and again — so once an answer is in the bank, the tool knows it forever.

The answers in this repo are the ones the challenge itself has shown. Nobody checked them against a book, so a wrong one can slip in; when the tool gets one wrong it marks that entry so you can fix it.

## What you need

- An Android phone with USB debugging turned on, Nusuk app installed and logged in
- A USB cable
- Python 3.8 or newer and ADB (Android platform-tools) on your PATH

## Running it

```bash
git clone https://github.com/cyberfantics/nusuk-question-automation.git
cd nusuk-question-automation
adb devices
python nusuk.py state       # see what is on the phone screen right now
python nusuk.py run -n 5    # answer up to 5 questions
```

`adb devices` should list your phone as `device`. If it says `unauthorized`, accept the prompt on the phone and run it again.

`run` stops on its own when it meets a question it does not know (exit code 3). Teach it with `learn` and run it again — the bank only grows.

## Options

```bash
python nusuk.py run -n 5                        # answer up to 5 questions
python nusuk.py run -n 10 --door quran          # only the Quran door
python nusuk.py run -n 5 --door any             # any door, picked in turn
python nusuk.py run -n 20 --max-seconds 600     # stop after 10 minutes
python nusuk.py state                           # what is on screen right now
python nusuk.py learn "Question?" "Answer"      # teach it a new question
python nusuk.py stats                           # how many questions the bank holds
```

Exit codes: 0 done, 3 unknown question (needs learning), 4 could not act.

## What is in here

| File | What it is |
| --- | --- |
| `nusuk.py` | The bot. Python, ADB and UI Automator. |
| `qa_bank.json` | The answers. A growing bank — every question the tool meets gets saved. |
| `answers.log` | Created when you run it. One line per answered question, right or wrong. |

## One thing to know

Questions repeat, so the bank is the whole point. Every question the tool answers gets a use count, and a wrong answer marks its entry as not verified, so you can fix it instead of the tool confidently repeating it. New questions stop the run instead of being guessed — the tool would rather stop than tap a wrong answer. Teach it with `learn` and it never stops on that one again.

## Adding your own questions

The easiest way is `learn`:

```bash
python nusuk.py learn "About whom was Surat al-Masad revealed?" "Abu Lahab and his wife"
```

Or edit `qa_bank.json` directly. Each entry is the question, its answer, and how many times it has been used. The script matches on the question text, so keep the wording as the app shows it.

## How it works, briefly

The script dumps the phone screen with UI Automator, reads the question and the options off it, and looks the question up in the bank. It matches exactly first, then falls back to a close match — but only if the words that flip a question's meaning (first, last, not, except, before, after, longest, shortest) are the same, so a near-identical question with the opposite answer never gets matched. Then it taps the option at its real position and taps Check your answer.

A few things that make it work on a real phone:

- No OCR. The app's own screen text is read straight from the UI dump.
- It polls for the screen to change instead of sleeping fixed seconds, so it moves on the moment the app reacts.
- The Check button is often clipped off the bottom of the screen, so the script scrolls the question sheet up until it has real bounds, and taps the full-width strip at the bottom edge when the label has none.
- If a stray tap lands in another app, it presses back twice and brings Nusuk back.
- A watchdog stops the run if it takes too many steps or gets stuck on one screen.

## If it breaks

| Problem | What to do |
| --- | --- |
| No Android device connected | Check the cable, turn on USB debugging, accept the prompt on the phone, run `adb devices`. |
| `adb` is not recognized | Install platform-tools and add it to PATH. |
| Unknown question, run stops (exit 3) | That is by design — teach it with `learn` and run it again. |
| It cannot read the question | Open the challenge to a question card yourself, then run `state` to see what the script sees. |
| A wrong answer keeps coming up | Check the entry in `qa_bank.json` and fix the answer; a wrong answer is marked not verified when it happens. |
| It gets stuck on one screen | The watchdog stops it. Run `state` to see where it is, open the question card yourself, and run it again. |
| Taps land in the wrong place | The script uses the option's real position when it can find it. If your screen is very different, open the question card first and let it start from there. |

## Where the questions came from

The challenge itself. The same questions come around again, so every question the tool has met is in the bank, with how many times it has been used. If you have more, teach them with `learn` or open a pull request.
