# Contributing to Whylog

Whylog stays small on purpose: one Python file, the standard library, and Git.

## Before opening a pull request

1. Fork the repository and create a focused branch.
2. Keep changes compatible with Python 3.9+ and Git 2.30+.
3. Add or update a test for behavior changes.
4. Run the checks below.

```bash
python -m py_compile whylog.py test_whylog.py
python -m unittest -v
python whylog.py --help
```

Pull requests should explain the problem and why the proposed change belongs
in the core tool. Please avoid new dependencies unless the standard library
cannot solve the problem safely.

## Reporting bugs

Open an issue with your operating system, Python and Git versions, the command
you ran, and the complete error output. Remove private prompts or repository
data before posting logs.
