# NPU media provenance

Selected Kotlin video pipeline and JNI wrapper files are adapted from
https://github.com/AbrahamPaulJ/nightmare-mobile at
`ddbeae20dbd3a9795d1d29883776be9c404bfd29` (v1.5.533), under CC BY-NC 4.0.
This component is non-commercial licensed; it is not covered by JieZhi's MIT license.
Changes: private file paths, isolated JieZhi service integration and runtime setup.
Upstream derives its image backend from https://github.com/xororz/local-dream .
The native executable/JNI and QNN libraries are extracted, unmodified, from the
pinned v1.5.533 release APK. See scripts/prepare-qnn.py for URL and SHA-256.
Qualcomm runtime/model terms apply separately. Original LICENSE and NOTICE follow.
