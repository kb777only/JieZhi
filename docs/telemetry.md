# Phone telemetry

Host 0.4 and Android client 0.4 add an always-visible bottom panel on every host
page. Each metric has a rolling two-minute line graph. Phone API readings refresh
once per second, ADB hardware readings every two seconds. Polling runs separately
from chat, upload and Assistant workers; only one telemetry request runs at a time.
Hover over a card or open **Sensor details** for its source and limitations.

| Metric | Source and meaning |
| --- | --- |
| Live ≈ tok/s | SDK token callbacks during the last two seconds, divided by two. This is an estimate: the SDK streams text without token IDs. The completed response retains the runtime's reported token rate separately. Includes reasoning emitted by a reasoning model. |
| Battery | Android battery level / scale, percent. |
| Battery temperature | Android battery temperature, converted from tenths of a degree Celsius. |
| SoC · CPU peak | Hottest current CPU temperature in Android's thermal HAL. Explicitly a CPU sensor proxy, not a single SoC die measurement. |
| CPU load | Difference between successive whole-phone `/proc/stat` counters; excludes idle and I/O wait, normalized across all cores. |
| GPU load | KGSL busy / total interval when the counter is readable. Unavailable on the tested Xiaomi's production firmware. |
| NPU load | Unavailable: no readable utilization counter was found on the tested phone. Requested NPU mode is not a load percentage. |
| RAM used | Whole-phone total RAM minus available RAM, in GiB. Includes Android and other apps. App PSS is listed separately in Sensor details and sampled every five seconds. |

Missing readings display a dash and gaps, never invented zeroes. Disconnects and
stale requests clear the current values. A different phone/forwarding session
starts fresh history. History is in memory only and not uploaded or saved by the
normal app. The development hardware-check script explicitly saves its samples.

On Xiaomi 15 Ultra / Android 16, CPU, GPU and NPU temperature sensors are readable
through ADB's current thermal-HAL output. Cached thermal entries are deliberately
ignored. The sensor called `socd` has electrical/BCL type 8 and reports a percentage;
it is **not** a temperature. Sensor details lists the actual temperature sensors.
GPU busy counters deny access on this firmware; NPU load is not exposed. JieZhi
makes neither rooting nor privileged profiler installation a requirement.

References: [Android BatteryManager](https://developer.android.com/reference/android/os/BatteryManager),
[Android thermal HAL temperature types](https://android.googlesource.com/platform/hardware/interfaces/+/refs/heads/main/thermal/aidl/android/hardware/thermal/TemperatureType.aidl),
and [GenieX Android API](https://github.com/qualcomm/GenieX/blob/main/docs/en/run/android/api-reference.mdx).
