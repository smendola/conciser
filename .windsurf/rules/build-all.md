---
trigger: always_on
---

## Chrome Extension

After changing code in chrome-extension, build the extension with:

```bash
python chrome-extension/build_extension.py
```

## Android

After changing code in android, do a release build:

```bash
cd android
./gradlew assembleRelease
```
