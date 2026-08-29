#!/usr/bin/env python3
"""lwcc 가중치 경로 버그 패치. Path("/.lwcc/weights") 절대경로 → ~/.lwcc/weights (2026-08-29 확인)."""
import importlib, pathlib
p = pathlib.Path(importlib.import_module("lwcc.util.functions").__file__)
s = p.read_text()
s2 = s.replace('Path("/.lwcc/weights").mkdir(parents=True, exist_ok=True)',
               'Path(os.path.join(str(Path.home()), ".lwcc", "weights")).mkdir(parents=True, exist_ok=True)') \
      .replace('os.path.join(home, "/.lwcc/weights/", file_name)', 'os.path.join(home, ".lwcc", "weights", file_name)')
p.write_text(s2); print("patched" if s2 != s else "already patched", p)
