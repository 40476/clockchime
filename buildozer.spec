[app]
(str) Title of your application
title = ClockChime

(str) Package name
package.name = clockchime

(str) Package domain (needed for android packaging)
package.domain = dev.usr40k

(str) Source code where the main.py live
source.dir = .

(list) Source files to include  (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,json

(str) Application versioning
version = 0.1

(list) Application requirementsnumpy and kivy are large, sounddevice requires libportaudio
requirements = python3,kivy,numpy,sounddevice,pillow

(list) Supported orientations
orientation = portrait

(bool) Indicate if the application should be fullscreen
fullscreen = 0

(list) Permissions
android.permissions = WAKE_LOCK, MODIFY_AUDIO_SETTINGS

(int) Target Android API
android.api = 33

(int) Minimum API your APK will support
android.minapi = 27

(str) Android NDK version to use
android.ndk = 25b

(bool) Automatically accept SDK license
android.accept_sdk_license = True

(str) The Android arch to build for
android.archs = arm64-v8a, armeabi-v7a[buildozer]

(int) Log level (2 = debug)
log_level = 2

(int) Display warning if buildozer is run as root
warn_on_root = 1
