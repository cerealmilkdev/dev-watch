#!/usr/bin/env python3
"""Scan secrets : fichiers suivis + historique git des clones locaux (~/dev).
Lecture seule. Sortie : liste de (repo, où, type, extrait masqué).
"""
import re
import subprocess
from pathlib import Path

DEV = Path.home() / "dev"
PATTERNS = [
    ("cle_privee_pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("openai_sk", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("anthropic_sk", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws_akid", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("hex64_secret", re.compile(r"[\"']?(?:jwt_secret_key|api_?secret|secret_key|private_key|passphrase)[\"']?\s*[:=]\s*[\"']([0-9a-fA-F]{32,}|[A-Za-z0-9/+_\-]{32,})[\"']", re.I)),
    ("eth_key", re.compile(r"\b0x[0-9a-fA-F]{64}\b")),
    ("mongo_pg_uri", re.compile(r"://[^\s:@/]+:[^\s:@/]{8,}@")),
    ("bearer_literal", re.compile(r"[\"']?Bearer\s+[A-Za-z0-9._\-]{25,}")),
    ("telegram_bot", re.compile(r"\b\d{8,12}:AA[A-Za-z0-9_\-]{30,}")),
]
IGNORE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".mp3", ".mp4", ".wav", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".lock", ".pdf", ".zip"}


def mask(s):
    s = s.strip()
    return s[:14] + "…" + (s[-4:] if len(s) > 20 else "")


def scan_text(text, where, out):
    for name, rx in PATTERNS:
        for m in rx.finditer(text):
            out.append((where, name, mask(m.group(0))))


def main():
    results = []
    for d in sorted(DEV.iterdir()):
        if not (d / ".git").is_dir():
            continue
        # fichiers suivis actuellement
        files = subprocess.run(["git", "-C", str(d), "ls-files"], capture_output=True, text=True).stdout.splitlines()
        for f in files:
            p = d / f
            if p.suffix.lower() in IGNORE_EXT or not p.is_file():
                continue
            try:
                if p.stat().st_size > 400_000:
                    continue
                scan_text(p.read_text(errors="ignore"), f"{d.name}/{f} (suivi)", results)
            except Exception:
                pass
        # historique (chemins touchés)
        hist = subprocess.run(["git", "-C", str(d), "log", "--all", "-p", "--no-color", "--unified=0"],
                              capture_output=True, text=True).stdout
        scan_text(hist, f"{d.name}/<historique>", results)
    # dédoublonne
    seen = set()
    for r in results:
        k = (r[0], r[1], r[2])
        if k in seen:
            continue
        seen.add(k)
        print(f"{r[1]:18} {r[0]:50} {r[2]}")
    print(f"\n{len(seen)} signal(aux)")


if __name__ == "__main__":
    main()
