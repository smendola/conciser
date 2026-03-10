---
trigger: always_on
---

After changing code in chrome-extension, run:
```bash
python chrome-extension/build_extension.py
```

After changing code in android, do a release build in the normal way.

Afer changing code affecing both clients, run:
```bash
scripts/build_all.sh
```