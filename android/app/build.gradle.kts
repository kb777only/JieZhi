import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "dev.jiezhi.client"
    compileSdk = 36
    defaultConfig {
        applicationId = "dev.jiezhi.client"
        minSdk = 31
        targetSdk = 36
        testInstrumentationRunner = "dev.jiezhi.client.MediaInstrumentation"
        versionCode = 7
        versionName = "0.7.0-alpha.1"
        ndk { abiFilters += "arm64-v8a" }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    packaging { jniLibs.useLegacyPackaging = true }
}
kotlin { compilerOptions { jvmTarget.set(JvmTarget.JVM_17) } }
dependencies {
    implementation("com.qualcomm.qti:geniex-android:0.7.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
    implementation("org.nanohttpd:nanohttpd:2.3.1")
}
