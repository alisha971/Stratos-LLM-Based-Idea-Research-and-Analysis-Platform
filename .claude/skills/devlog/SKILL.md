---
name: devlog
description: Write a personal, first-person build-log entry about what was worked on — what was tried, what broke, what got changed as a result, and the concepts I asked Claude to explain (each with a worked example). Use when the user runs /devlog, or asks to "write up today", "log this", "add to my build notes", typically at the end of a session or after a commit/push. Can span several of the day's chats — the user picks which.
---

# Devlog

Personal build notes for Stratos. Not documentation, not a changelog, not a summary for anyone else — these are the user's own notes about what they tried while building, in their own voice.

**Where:** `stratos-devlog/YYYY-MM-DD.md` (repo root, gitignored, local only). One file per day; a second `/devlog` on the same day appends new sections to the same file, it does not overwrite.

## Two kinds of entry

1. **What broke and what I changed** — the story sections. Voice and rules below.
2. **Things I didn't know going in** — every place I said "I don't know this", "why did you pick that", "explain this to me", "what does this even do". Each becomes a short concept note that **must carry a concrete worked example** from the actual code or run — never a textbook definition floating on its own.

## The voice — this is the whole point

Written **in first person, as a student experimenting**. The subject of every sentence is the user doing something: *I tried, I assumed, I got stuck, I ripped it out, I gave up on that and did this instead.*

Each entry is a **short headed section**: one plain-language heading naming the thing worked on, then 1–3 short paragraphs telling the story of it. The story shape is almost always:

> what I set out to do → what I tried first → how it failed → what I figured out → what I did instead → where it landed

Good:

> ### Clarification worker kept asking irrelevant questions
>
> I thought the fix was a better prompt so I rewrote it twice, added examples, made it stricter. No change. Eventually I logged the actual payload and saw I was only sending the original idea, never the prior answers — so of course it repeated itself.
>
> Threading the prior turns in fixed it. Note to self: log the payload before rewriting the prompt.

Bad (this is the failure mode to avoid — a decision register, not notes):

> ### Clarification worker
> - Decision: include prior turns in context
> - Rationale: model lacked conversation state
> - Outcome: resolved

### Rules

- **Never a bulleted list of decisions.** Prose paragraphs under each heading. Bullets only if the user is genuinely listing things (e.g. four env vars added), never for the reasoning.
- **Dead ends are the valuable part.** The thing tried that didn't work matters more than the thing that shipped. If a section has no struggle in it, it's probably not worth a section — fold it into a one-line "also" paragraph.
- **Plain words.** "It kept timing out", not "latency degradation was observed". No corporate register, no "successfully implemented", no "leveraged".
- **Uncertainty stays in.** "I still don't really know why that fixed it" is a legitimate and useful line. Don't tidy it into false confidence.
- **Headings are descriptive, not categorical.** "Groq kept truncating JSON mid-object" beats "LLM changes".
- **Short.** 2–5 story sections per entry, a few paragraphs each. If the day was quiet, one section is fine.
- **No praise, no summary-of-summary.** Don't open with "Productive day!" or close with "Overall good progress". Start with the first thing worked on, end when the last thing is told.

## Concept notes — "Things I didn't know going in"

Go under a single `## Things I didn't know going in` H2 for the day, each concept its own H3.

**When to make one.** Scan the selected chats for moments where I asked to be *taught* something, not just helped. Trigger phrases: "I don't know", "no idea", "not sure what", "why did you", "why do you", "why this", "why that", "why choose", "why suggest", "why go with", "explain", "what is", "what does", "what's the difference", "how does this work", "in simple terms", "eli5", "I don't get", "I don't understand", "confused about". One distinct concept per note — collapse repeats of the same question into one.

**Shape of a concept note:**

- One plain-language line stating the thing I didn't get.
- 1–2 short first-person paragraphs: what I thought it was → what it actually is.
- **A worked example, always.** Pulled from this repo or the run we were staring at — a real file path, a real payload, a real value, a before/after snippet, the actual error. If the chat only explained it in the abstract, go get the example from the codebase or the diff *now* before writing the note. **A concept note with no concrete example is not finished.**

Good:

> ### What Redis pub/sub is actually doing in our pipeline
>
> I thought Redis was just the Celery job queue. It's also the channel a worker uses to tell the orchestrator "I'm done" without either of them calling the other directly.
>
> Real example from our code: `research_worker` finishes and calls `publish_event("research.completed", session_id)` in `app/utils/redis_pub.py`. `redis_sub.py` is subscribed to the `stratos_events` channel, catches that, and `orchestrator_service` flips the session from `RESEARCH` to `SECTION`. There is no HTTP call between them — the channel is the seam. That's also why the Thread-2 `TimeoutError` on 27 Aug froze the run: Redis was unreachable, the "done" message never landed, and the session just sat in `RESEARCH`.

Bad (abstract, no example — do not do this):

> ### Redis pub/sub
> Publish/subscribe is a messaging pattern where senders publish messages to channels without knowledge of the subscribers, which decouples components.

## Which chats to cover

The **current conversation is always included.** Beyond that, one day can span several chats and the user decides which ones count — a single specific chat, a group, or all of them.

1. **List the day's candidate chats.** Run the list script (below). Output is a numbered list: date, start time, short session id, turn count, and a one-line gist taken from the first real prompt. If a first prompt is too vague to tell what the chat was about, skim that transcript's clean dump and write a better one-liner yourself before showing the list.

2. **Show the list and ask which to process.** Plain text is fine — "all of them", specific numbers, or a single one. **Wait for the answer; never assume.** If the user already named the scope (e.g. `/devlog chats 2 and 4`), skip the prompt.

3. **Dump the chosen chats to clean text and read them.** Run the extract script (below) for the chosen ids; it writes `<id>.txt` files of `ME:` / `CLAUDE:` turns with tool noise stripped, into the scratchpad. Read each one. These, plus the current conversation, are the source for both kinds of entry.

### Scripts

Transcript dir (Claude Code stores one `.jsonl` per chat here):

```bash
DIR=$(ls -d ~/.claude/projects/*stratos* 2>/dev/null | head -1)
# fallback if empty: DIR="$HOME/.claude/projects/c--Users-admin-Desktop-VSCode-stratos"
```

**List mode** — `python list.py "$DIR" [YYYY-MM-DD]` (omit the date to list every chat):

```python
import json, sys, glob, os
d = sys.argv[1]; day = sys.argv[2] if len(sys.argv) > 2 else None
rows = []
for f in glob.glob(os.path.join(d, '*.jsonl')):
    first = None; prompts = []
    with open(f, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try: o = json.loads(line)
            except: continue
            if o.get('type') != 'user': continue
            if not first: first = o.get('timestamp')
            c = o.get('message', {}).get('content')
            txt = ' '.join(p.get('text', '') for p in c if isinstance(p, dict) and p.get('type') == 'text') if isinstance(c, list) else (c or '')
            txt = ' '.join(txt.split())
            if txt and not txt.startswith('<') and 'Caveat:' not in txt[:60]:
                prompts.append(txt)
    if not prompts or not first: continue
    if day and first[:10] != day: continue
    rows.append((first, os.path.basename(f)[:8], len(prompts), prompts[0][:110]))
rows.sort()
for i, (first, sid, n, head) in enumerate(rows, 1):
    print(f'{i:2}. {first[:10]} {first[11:16]}  {sid}  {n:2} turns  | {head}')
```

**Extract mode** — `python extract.py "$DIR" <out_dir> <id> [<id> ...]` (ids are the 8-char short ids from the list):

```python
import json, sys, os, glob
d, outdir = sys.argv[1], sys.argv[2]; ids = set(sys.argv[3:])
os.makedirs(outdir, exist_ok=True)
for f in glob.glob(os.path.join(d, '*.jsonl')):
    sid = os.path.basename(f)[:8]
    if ids and sid not in ids: continue
    out = []
    with open(f, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try: o = json.loads(line)
            except: continue
            ty = o.get('type')
            if ty not in ('user', 'assistant'): continue
            c = o.get('message', {}).get('content')
            if isinstance(c, list):
                txt = '\n'.join(p.get('text', '') for p in c if isinstance(p, dict) and p.get('type') == 'text')
            else:
                txt = c or ''
            txt = txt.strip()
            if not txt or txt.startswith('<'): continue
            if ty == 'user' and 'Caveat:' in txt[:60]: continue
            out.append(('ME: ' if ty == 'user' else 'CLAUDE: ') + txt)
    if out:
        open(os.path.join(outdir, sid + '.txt'), 'w', encoding='utf-8').write('\n\n'.join(out))
        print('wrote', sid, len(out), 'msgs')
```

## Procedure

1. **Find the last entry** so you know the window to cover:
   `ls stratos-devlog/ 2>/dev/null | tail -3`
   Read the most recent one — it tells you what's already been written up (don't repeat it) and reminds you of the established voice.

2. **Pick the chats.** Follow "Which chats to cover" — list the day's chats, let the user choose, dump and read the chosen transcripts. The current conversation is always in scope.

3. **Gather what happened.** From all three:
   - **The selected chats + this conversation.** The primary source. What was attempted, what errored, what got abandoned, what the user pushed back on, and every "I don't know / why / explain this" moment.
   - **Git, since the last entry:**
     ```bash
     git log --oneline --since="<date of last entry>"
     git diff --stat HEAD~<n>
     git status --short
     ```
     Use the diff to catch work the conversation didn't cover and to get specifics right (file names, actual values).

4. **Scan for concept moments.** Grep the clean transcript dumps for the trigger phrases in "Concept notes". Each hit is a candidate concept note; group duplicates of the same question. For each one you keep, make sure you have a real example — go pull it from the code or diff if the chat didn't give one.

5. **Find the gaps, then ask.** Before writing, list the things where you can see *what* changed but not *why* — a reverted approach, a value that got tuned, a file that got deleted, a decision made in a chat with thin explanation. **Ask the user 2–3 targeted questions** (AskUserQuestion, or plain text). Ask about their reasoning and their frustration, not facts you can read from the diff:
   - "You swapped the Groq model — was the old one actually breaking, or was it a speed thing?"
   - "What was the thing that made you give up on the sync version?"

   Skip only if the material already covers the why for everything worth writing about.

6. **Write it.** Append to today's file, or create it with an `# <Day> <Month> <Year>` H1 if it's new. Story sections are H3 under it. Concept notes are H3 under a single `## Things I didn't know going in` H2. Every concept note carries its worked example. Match the voice of previous entries.

7. **Show the user what you wrote** (the entry text itself, not a description of it) and offer to adjust. These are their notes — if the story is wrong, it's worth fixing on the spot.

## First run

If `stratos-devlog/` doesn't exist, create it and check it's ignored — `git check-ignore stratos-devlog/` should exit 0. If not, add `stratos-devlog/` to `.gitignore` under the project-specific section. These notes are never committed.

## Arguments

- `/devlog` — cover everything since the last entry; prompts for which of the day's other chats to include.
- `/devlog chats` — go straight to the chat picker for today.
- `/devlog chats <n> <n> ...` — process exactly those numbered chats from today, no prompt.
- `/devlog <topic>` — write up just that one thing (e.g. `/devlog the astra migration`), even if other work happened.
- `/devlog backfill` — reconstruct entries for past work from git history and the planning docs. Ask the user about the why before writing; a backfill is mostly reconstruction and will read hollow without their input. Date backfilled files by the day the work happened, and add `*(written later, from memory)*` under the H1.
