# find_urls.py — Run from project root (same dir as manage.py)
import os
import re

ROOT = os.getcwd()
EXCLUDE_DIRS = {'venv', '.venv', '.git', 'media', '__pycache__', 'node_modules'}
PATTERNS = [
    re.compile(r"""\{\%\s*url\s+['"]create['"]"""),
    re.compile(r"""\{\%\s*url\s+['"]list['"]"""),
    re.compile(r"""\{\%\s*url\s+['"]detail['"]"""),
    re.compile(r"""\{\%\s*url\s+['"]edit['"]"""),
]

matches = []

for dirpath, dirnames, filenames in os.walk(ROOT):
    # skip excluded dirs
    parts = set(dirpath.replace(ROOT, '').split(os.sep))
    if parts & EXCLUDE_DIRS:
        continue

    for fname in filenames:
        if not fname.endswith(('.html', '.htm', '.txt')):
            continue
        fpath = os.path.join(dirpath, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, start=1):
                    for pat in PATTERNS:
                        if pat.search(line):
                            matches.append((fpath, i, line.strip()))
        except (PermissionError, OSError) as e:
            # safe to ignore files we can't read
            continue

if not matches:
    print("No matches found for common un-namespaced url patterns in scanned templates.")
else:
    print("Found possible un-namespaced URL usages:")
    for fpath, lineno, line in matches:
        print(f"{fpath}:{lineno}: {line}")

