#!/bin/sh
# Reproducible, CPU-only ARM64 diffusion executable. No desktop model runtime.
set -eu
cd "$(dirname "$0")/.."
revision=c678dfe704a2230342376b46add9c8ca736a653d
sdk_root="${ANDROID_HOME:-$PWD/.tools/android-sdk}"
ndk_root="$sdk_root/ndk/27.2.12479018"
cmake_bin="$sdk_root/cmake/3.22.1/bin/cmake"
git_bin="${GIT:-git}"
if ! test -f "$ndk_root/build/cmake/android.toolchain.cmake" || ! test -x "$cmake_bin"; then
    printf '%s\n' 'Install Android SDK packages ndk;27.2.12479018 and cmake;3.22.1 first.' >&2
    exit 1
fi
if ! test -d .tools/stable-diffusion.cpp/.git; then
    "$git_bin" clone https://github.com/leejet/stable-diffusion.cpp .tools/stable-diffusion.cpp
fi
if ! "$git_bin" -C .tools/stable-diffusion.cpp cat-file -e "$revision^{commit}"; then
    "$git_bin" -C .tools/stable-diffusion.cpp fetch origin "$revision"
fi
"$git_bin" -C .tools/stable-diffusion.cpp checkout --detach "$revision"
"$git_bin" -C .tools/stable-diffusion.cpp submodule update --init --recursive
"$cmake_bin" -S .tools/stable-diffusion.cpp -B .tools/sd-android -G Ninja \
    -DCMAKE_MAKE_PROGRAM="$sdk_root/cmake/3.22.1/bin/ninja" \
    -DCMAKE_TOOLCHAIN_FILE="$ndk_root/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31 -DANDROID_STL=c++_static \
    -DCMAKE_BUILD_TYPE=Release -DGGML_OPENMP=OFF -DSD_WEBP=OFF -DSD_WEBM=OFF -DBUILD_SHARED_LIBS=OFF
"$cmake_bin" --build .tools/sd-android --target sd-cli -j "${JOBS:-3}"
mkdir -p android/app/src/main/jniLibs/arm64-v8a
cp .tools/sd-android/bin/sd-cli android/app/src/main/jniLibs/arm64-v8a/libjiezhi_diffusion.so
"$ndk_root/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" android/app/src/main/jniLibs/arm64-v8a/libjiezhi_diffusion.so
mkdir -p android/app/src/main/assets/media-licenses
cp .tools/stable-diffusion.cpp/LICENSE android/app/src/main/assets/media-licenses/stable-diffusion-MIT.txt
cp .tools/stable-diffusion.cpp/ggml/LICENSE android/app/src/main/assets/media-licenses/ggml-MIT.txt
cp .tools/stable-diffusion.cpp/thirdparty/oniguruma/COPYING android/app/src/main/assets/media-licenses/oniguruma.txt
cp .tools/stable-diffusion.cpp/thirdparty/utf8proc/LICENSE.md android/app/src/main/assets/media-licenses/utf8proc.txt
cp .tools/stable-diffusion.cpp/thirdparty/LICENSE.darts_clone.txt android/app/src/main/assets/media-licenses/darts-clone.txt
cp .tools/stable-diffusion.cpp/thirdparty/*.h android/app/src/main/assets/media-licenses/
cp "$ndk_root/NOTICE.toolchain" android/app/src/main/assets/media-licenses/android-toolchain-NOTICE.txt
