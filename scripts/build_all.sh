#!/bin/bash -e

# Read and increment build number
BUILD_NUMBER_FILE="build_number"
if [ ! -f "$BUILD_NUMBER_FILE" ]; then
  echo "Build number file not found. Creating one."
  echo 0 > "$BUILD_NUMBER_FILE"
fi

BUILD_NUMBER=$(cat "$BUILD_NUMBER_FILE")
BUILD_NUMBER=$((BUILD_NUMBER + 1))
echo $BUILD_NUMBER > "$BUILD_NUMBER_FILE"

VERSION="1.0.$BUILD_NUMBER"
echo "Building version $VERSION"

# Update Android version
ANDROID_GRADLE_FILE="android/app/build.gradle"
sed -i "s/versionName \".*\"/versionName \"$VERSION\"/" "$ANDROID_GRADLE_FILE"
sed -i "s/versionCode .*/versionCode $BUILD_NUMBER/" "$ANDROID_GRADLE_FILE"

# Update Chrome Extension version
CHROME_MANIFEST_FILE="chrome-extension/manifest.json"
sed -i 's/"version": ".*"/"version": "'$VERSION'"/' "$CHROME_MANIFEST_FILE"

(
  cd chrome-extension
  python build_extension.py
)

(
  cd android
  ./gradlew assembleRelease
)
