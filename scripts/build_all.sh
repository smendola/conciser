#!/bin/bash -e

(
  cd chrome-extension
  python build_extension.py
)

(
  cd android
  ./gradlew assembleRelease
)
