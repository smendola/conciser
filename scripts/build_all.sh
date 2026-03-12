#!/bin/bash -e

echo "Building Android + Chrome extension"

ANDROID_BUILD_NUMBER_FILE="android/.build_number"
CHROME_BUILD_NUMBER_FILE="chrome-extension/.build_number"

if [ ! -f "$ANDROID_BUILD_NUMBER_FILE" ]; then
  echo "0" > "$ANDROID_BUILD_NUMBER_FILE"
fi

if [ ! -f "$CHROME_BUILD_NUMBER_FILE" ]; then
  echo "0" > "$CHROME_BUILD_NUMBER_FILE"
fi

(
  cd chrome-extension
  python build_extension.py
)

(
  cd android
  ./gradlew assembleRelease
)
