OplusLauncher.apk = Zuyqa modded launcher 17.3.9 (user supplied 2026-11-02:
"System-Laucher-17.3.9-Powered-By-Zuyqa (layout fix).zip", a Magisk/KSU module; its apk md5
46fcf1e3865de3ee61df96e971aa9970, stock Oplus platform certificate, content modified) plus:
  - Home screen search button: Breeno option -> Google (opens the Google app search box,
    android.search.action.GLOBAL_SEARCH); pill text "Ask anything" -> "Ask Google"
  - "ZuyQA / Powered By ZuyQA ... Translated By ArticPorts" headers removed from Home screen settings
    and Custom features; versionName "17.3.9-Powered By Zuyqa" -> "17.3.9"
Rebuild: python3 -I src/patch_google.py ORIGINAL.apk OplusLauncher.apk  (run from this folder; uses the
kit's lib/ and tools/). ORIGINAL.apk is the apk inside the Zuyqa module zip (md5 46fcf1e3...); it is not
shipped with the kit, so keep the module zip if you want to rebuild. Builds only need OplusLauncher.apk.
build_port.py drops it into system_ext/priv-app/OplusLauncher (replaces the old dock/liquid glass patch, now retired). Built into the image it needs no root/module.
