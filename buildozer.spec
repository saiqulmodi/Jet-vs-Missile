[app]
title = Jet vs Missile
package.name = jetvsmissile
package.domain = org.saiqul
source.dir = .
source.include_exts = py
source.exclude_dirs = build, bin, .buildozer, __pycache__, tools, venv, docs, icons, tests, .git, p4a-recipes
source.exclude_patterns = buildozer.spec*, conftest.py
version = 2.0
android.numeric_version = 200
requirements = python3,pygame
p4a.bootstrap = sdl2
p4a.local_recipes = ./p4a-recipes
orientation = landscape
fullscreen = 1
icon.filename = %(source.dir)s/icons/icon.png
android.presplash_color = #0A0E16
android.api = 36
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.release_artifact = aab
android.debug_artifact = apk
android.wakelock = True

[buildozer]
log_level = 2
warn_on_root = 1
