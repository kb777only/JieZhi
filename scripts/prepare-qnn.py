#!/usr/bin/env python3
"""Stage a pinned NPU backend for this non-commercial prototype build.

Native files are unmodified components from Nightmare Mobile / LocalDream.
CC BY-NC 4.0 and Qualcomm runtime terms apply; see third_party/nightmare-mobile.
"""
import hashlib
from pathlib import Path
import shutil
import urllib.request
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
URL='https://github.com/AbrahamPaulJ/nightmare-mobile/releases/download/v1.5.533/nightmare-1.5.533.apk'
SHA='52b21b822160c7741f012dbc0e54d96839ffc97bedb4a6380905748c1c0d4c3c'
cache=ROOT/'.cache/nightmare-mobile.apk';cache.parent.mkdir(exist_ok=True)
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024**2):h.update(block)
    return h.hexdigest()
if not cache.is_file() or digest(cache)!=SHA:
    part=cache.with_suffix('.partial')
    with urllib.request.urlopen(URL,timeout=60) as response,part.open('wb') as out:shutil.copyfileobj(response,out)
    if digest(part)!=SHA:part.unlink();raise RuntimeError('NPU runtime checksum mismatch')
    part.replace(cache)
with ZipFile(cache) as archive:
    for name in archive.namelist():
        target=None
        if name in ['lib/arm64-v8a/libstable_diffusion_core.so','lib/arm64-v8a/libnmqnn.so']:
            target=ROOT/'android/app/src/main/jniLibs/arm64-v8a'/Path(name).name
        elif name.startswith('assets/qnnlibs/') and ('V79' in name or Path(name).name in ['libQnnHtp.so','libQnnSystem.so']):
            target=ROOT/'android/app/src/main/assets/qnnlibs'/Path(name).name
        elif name.startswith('assets/npu/canary'):
            target=ROOT/'android/app/src/main'/name
        if target:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(name))
notices=ROOT/'android/app/src/main/assets/media-licenses/nightmare-mobile';notices.mkdir(parents=True,exist_ok=True)
for name in ['LICENSE','NOTICE','README.md']:shutil.copy2(ROOT/'third_party/nightmare-mobile'/name,notices/name)
print('Verified and staged NPU runtime v1.5.533 (Snapdragon 8 Elite / V79).')
