#!/usr/bin/env python3
"""
Sentiment labeling tool for forum posts.

Loads a stratified sample (by forum, year, message length) and lets you
annotate each post with a sentiment label:
  0 = Negative   1 = Neutral   2 = Positive

Stops automatically when the rarest class reaches TARGET_PER_CLASS labels.
Progress is saved after every label so you can quit and resume freely.

Run:
  cd sentiment-labeling
  uv run --project ../sentiment python label.py
"""

import sys
import signal
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
SOURCE       = SCRIPT_DIR.parent / "sentiment" / "data" / "cleaned_forum_posts.parquet"
QUEUE_FILE   = SCRIPT_DIR / "data" / "sample_queue.parquet"
LABELS_FILE  = SCRIPT_DIR / "data" / "labeled.parquet"

TARGET_PER_CLASS = 500
QUEUE_PER_STRATUM = 200  # max records sampled per (forum × year × length_bin)

LABEL_NAMES  = {0: "Negative", 1: "Neutral", 2: "Positive"}

# ── ANSI helpers ──────────────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
RED   = "\033[31m"
YEL   = "\033[33m"
GRN   = "\033[32m"
CYN   = "\033[36m"

def c(*codes):
    """Return an ANSI formatter function."""
    return lambda text: "".join(codes) + str(text) + RESET

bold   = c(BOLD)
dim    = c(DIM)
red    = c(RED)
yel    = c(YEL)
grn    = c(GRN)
cyn    = c(CYN)

LABEL_COLOR = {0: red, 1: yel, 2: grn}

# ── Stratified queue ──────────────────────────────────────────────────────────
def build_queue(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    df = df.copy()
    df["_len_bin"] = pd.qcut(
        df["message_length"], q=3, labels=["short", "medium", "long"]
    )
    rng = np.random.default_rng(seed)
    parts = []
    for _, grp in df.groupby(["forum", "year", "_len_bin"], observed=True):
        n = min(len(grp), QUEUE_PER_STRATUM)
        parts.append(grp.sample(n=n, random_state=int(rng.integers(1_000_000))))
    queue = (
        pd.concat(parts)
        .drop(columns=["_len_bin"])
        .sample(frac=1, random_state=seed)
        .reset_index(drop=True)
    )
    return queue


def load_or_build_queue(df: pd.DataFrame) -> pd.DataFrame:
    if QUEUE_FILE.exists():
        return pd.read_parquet(QUEUE_FILE)
    print(cyn("Building stratified sample queue…"))
    queue = build_queue(df)
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    queue.to_parquet(QUEUE_FILE, index=False)
    print(cyn(f"Queue: {len(queue):,} records — "
              f"{queue['forum'].nunique()} forums, {queue['year'].nunique()} years."))
    return queue

# ── Labels store ──────────────────────────────────────────────────────────────
def load_labels() -> pd.DataFrame:
    if LABELS_FILE.exists():
        return pd.read_parquet(LABELS_FILE)
    # Full row + label columns
    return pd.DataFrame()


def append_label(row: pd.Series, sentiment: int, labels: pd.DataFrame) -> pd.DataFrame:
    entry = row.to_dict()
    entry["sentiment"]  = sentiment
    entry["labeled_at"] = datetime.now().isoformat()
    new_row = pd.DataFrame([entry])
    labels = pd.concat([labels, new_row], ignore_index=True)
    LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    labels.to_parquet(LABELS_FILE, index=False)
    return labels

# ── Display ───────────────────────────────────────────────────────────────────
def class_counts(labels: pd.DataFrame) -> dict[int, int]:
    counts = {0: 0, 1: 0, 2: 0}
    if len(labels) and "sentiment" in labels.columns:
        for k, v in labels["sentiment"].value_counts().items():
            counts[int(k)] = int(v)
    return counts


def print_progress(labels: pd.DataFrame):
    counts  = class_counts(labels)
    total   = sum(counts.values())
    min_cnt = min(counts.values())
    to_go   = max(0, TARGET_PER_CLASS - min_cnt)
    width   = 30

    print()
    print(bold(f"  {total} labeled · rarest class at {min_cnt}/{TARGET_PER_CLASS} · {to_go} to go"))
    for cls, name in LABEL_NAMES.items():
        n      = counts[cls]
        filled = min(int(width * n / TARGET_PER_CLASS), width)
        bar    = "█" * filled + "░" * (width - filled)
        pct    = min(100, int(100 * n / TARGET_PER_CLASS))
        marker = dim(" ← rarest") if n == min_cnt and total > 0 else ""
        print(f"  {LABEL_COLOR[cls](f'{name:<10}')}  [{bar}]  {n:>3}/{TARGET_PER_CLASS}{marker}")
    print()


def print_post(row: pd.Series, queue_pos: int, queue_total: int):
    ticker  = row.get("ticker", "?")
    company = row.get("company_name", "?")
    date    = pd.Timestamp(row["date_time"]).date()

    print("\n" + "─" * 72)
    print(dim(f"  [{queue_pos}/{queue_total}]  {row['forum']}  ·  {date}  ·  {company} ({ticker})"))
    print("─" * 72 + "\n")

    for line in str(row["message"]).split("\n"):
        print(f"  {line}")
    print()

# ── Main ──────────────────────────────────────────────────────────────────────
PROMPT = bold("  Label [0=neg / 1=neu / 2=pos / s=skip / p=progress / q=quit]: ")


def main():
    print(bold(cyn("\n  Forum Post Sentiment Labeler")))
    print(dim("  0=Negative  1=Neutral  2=Positive  s=Skip  p=Progress  q=Quit\n"))

    print(dim("  Loading data…"))
    df     = pd.read_parquet(SOURCE)
    queue  = load_or_build_queue(df)
    labels = load_labels()

    labeled_ids   = set(labels["id"].tolist()) if len(labels) else set()
    pending_queue = queue[~queue["id"].isin(labeled_ids)].reset_index(drop=True)

    counts = class_counts(labels)
    if min(counts.values()) >= TARGET_PER_CLASS:
        print(grn(bold(f"\n  Already done — all classes have {TARGET_PER_CLASS}+ labels.")))
        print_progress(labels)
        return

    print_progress(labels)

    # Mutable ref so the signal handler can see the latest labels
    state = {"labels": labels}

    def on_exit(sig=None, frame=None):
        total = sum(class_counts(state["labels"]).values())
        print(cyn(f"\n\n  Session ended. {total} labels saved. Resume any time."))
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)

    for queue_pos, (_, row) in enumerate(pending_queue.iterrows(), start=1):
        counts = class_counts(state["labels"])
        if min(counts.values()) >= TARGET_PER_CLASS:
            break

        print_post(row, queue_pos, len(pending_queue))

        while True:
            try:
                raw = input(PROMPT).strip().lower()
            except EOFError:
                on_exit()

            if raw == "q":
                on_exit()
            elif raw == "p":
                print_progress(state["labels"])
            elif raw == "s":
                print(dim("  Skipped."))
                break
            elif raw in ("0", "1", "2"):
                sentiment = int(raw)
                state["labels"] = append_label(row, sentiment, state["labels"])
                print(LABEL_COLOR[sentiment](f"  Saved: {LABEL_NAMES[sentiment]}"))

                counts = class_counts(state["labels"])
                if min(counts.values()) >= TARGET_PER_CLASS:
                    print(grn(bold(f"\n  Target reached — all classes have {TARGET_PER_CLASS}+ labels!")))
                    print_progress(state["labels"])
                    return
                break
            else:
                print(red("  Invalid — use 0, 1, 2, s, p, or q."))

    counts = class_counts(state["labels"])
    if min(counts.values()) < TARGET_PER_CLASS:
        print(yel("\n  Queue exhausted before hitting target."))
        print(yel("  Delete data/sample_queue.parquet and re-run to generate a fresh queue."))

    print_progress(state["labels"])


if __name__ == "__main__":
    main()
