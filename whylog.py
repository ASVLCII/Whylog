#!/usr/bin/env python3
"""Whylog: store and query engineering intent in Git notes."""

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import subprocess
import sys

NOTES_REF = "refs/notes/ai"
COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def paint(code, text):
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def status(symbol, text, detail=""):
    suffix = paint("2", f"  {detail}") if detail else ""
    print(f"{paint('36;1', symbol)} {text}{suffix}")


def git(*args, check=True):
    result = subprocess.run(
        ["git", *args], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, encoding="utf-8"
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def read_note(oid):
    result = subprocess.run(
        ["git", "notes", f"--ref={NOTES_REF}", "show", oid], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, encoding="utf-8"
    )
    if result.returncode:
        return []
    value = json.loads(result.stdout)
    return value if isinstance(value, list) else [value]


def write_note(oid, entry):
    entries = read_note(oid)
    if not any(item.get("id") == entry["id"] for item in entries):
        entries.append(entry)
    git("notes", f"--ref={NOTES_REF}", "add", "-f", "-m",
        json.dumps(entries, separators=(",", ":")), oid)


def configure_rewrites():
    refs = git("config", "--get-all", "notes.rewriteRef", check=False).splitlines()
    if NOTES_REF not in refs:
        git("config", "--add", "notes.rewriteRef", NOTES_REF)


def command_log(args):
    if args.type == "Watch" and not (args.watch_glob and args.watch_run):
        raise ValueError("Watch requires --watch-glob and --watch-run")
    commit = git("rev-parse", args.commit)
    stamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    prompt_sha = "sha256:" + hashlib.sha256(args.prompt.encode()).hexdigest()
    seed = "\0".join((args.type, args.why, prompt_sha, args.model, stamp))
    entry = {
        "id": "w" + hashlib.sha256(seed.encode()).hexdigest()[:10],
        "type": args.type, "why": args.why, "prompt_sha": prompt_sha,
        "model": args.model, "ts": stamp,
    }
    if args.type == "Watch":
        entry["watch"] = {"glob": args.watch_glob, "run": args.watch_run}

    configure_rewrites()
    targets = [(commit, "commit")]
    for path in args.file:
        targets.append((git("rev-parse", f"{commit}:{path}"), path))
    for index, (oid, label) in enumerate(targets, 1):
        write_note(oid, entry)
        status(">", f"linked {label}", f"{index}/{len(targets)}  {oid[:10]}")
    status("+", paint("32;1", f"saved {entry['id']}"), entry["type"])


def parse_location(value):
    path, separator, line = value.rpartition(":")
    if not separator or not path or not line.isdigit() or int(line) < 1:
        raise ValueError("location must be path:line")
    return path, int(line)


def command_why(args):
    path, line = parse_location(args.location)
    blame = git("blame", "--porcelain", "-L", f"{line},{line}", "--", path)
    commit = blame.split(None, 1)[0]
    if set(commit) == {"0"}:
        raise RuntimeError("line is not committed")
    blob = git("rev-parse", f"{commit}:{path}")
    entries = read_note(blob) or read_note(commit)
    if not entries:
        raise RuntimeError("no intent recorded for this line")
    status("@", paint("35;1", f"{path}:{line}"), commit[:10])
    for entry in entries:
        print(f"  {paint('36;1', entry['type'].upper())}  {entry['why']}")
        print(paint("2", f"  {entry['id']}  {entry['model']}  {entry['prompt_sha']}"))


def all_entries():
    seen = set()
    rows = []
    for row in git("notes", f"--ref={NOTES_REF}", "list", check=False).splitlines():
        target = row.split()[-1]
        for entry in read_note(target):
            if entry["id"] not in seen:
                seen.add(entry["id"])
                rows.append(entry)
    return sorted(rows, key=lambda item: item["ts"], reverse=True)


def command_list(args):
    entries = [e for e in all_entries() if not args.type or e["type"] == args.type]
    status("#", paint("35;1", "intent log"), f"{len(entries)} entries")
    for entry in entries:
        print(f"  {paint('36;1', entry['id'])}  {entry['type']:<8} {entry['why']}")


def command_check(_args):
    changed = set(git("diff", "--name-only", "HEAD", check=False).splitlines())
    changed.update(git("ls-files", "--others", "--exclude-standard", check=False).splitlines())
    watches = [e for e in all_entries() if e["type"] == "Watch"]
    selected = [e for e in watches if any(fnmatch.fnmatch(path, e["watch"]["glob"]) for path in changed)]
    status("#", paint("35;1", "watch checks"), f"{len(selected)}/{len(watches)} triggered")
    failed = 0
    for entry in selected:
        result = subprocess.run(entry["watch"]["run"], shell=True)
        failed += result.returncode != 0
        status("+" if result.returncode == 0 else "x",
               entry["why"], "passed" if result.returncode == 0 else "failed")
    if failed:
        raise RuntimeError(f"{failed} watch check(s) failed")


def parser():
    root = argparse.ArgumentParser(prog="whylog", description="Git as an intent database")
    commands = root.add_subparsers(dest="command", required=True)
    log = commands.add_parser("log", help="attach intent to a commit and its blobs")
    log.add_argument("--type", choices=("Decision", "Rejected", "Watch"), required=True)
    log.add_argument("--why", required=True)
    log.add_argument("--prompt", default="")
    log.add_argument("--model", required=True)
    log.add_argument("--commit", default="HEAD")
    log.add_argument("--file", action="append", default=[])
    log.add_argument("--watch-glob")
    log.add_argument("--watch-run")
    log.set_defaults(handler=command_log)
    why = commands.add_parser("why", help="explain a committed line")
    why.add_argument("location")
    why.set_defaults(handler=command_why)
    listing = commands.add_parser("list", help="show recorded intent")
    listing.add_argument("--type", choices=("Decision", "Rejected", "Watch"))
    listing.set_defaults(handler=command_list)
    check = commands.add_parser("check", help="run matching Watch checks")
    check.set_defaults(handler=command_check)
    return root


def main():
    try:
        args = parser().parse_args()
        args.handler(args)
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        status("x", paint("31;1", "error"), str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
