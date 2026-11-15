smali/baksmali 3.0.10 (Google's maintained fork, com.android.tools.smali) and its runtime dependencies, from
Google Maven (dl.google.com/android/maven2/com/android/tools/smali/). Used only for framework.jar: smali 2.5.2
fails on its newer hidden-API flags. Run as:
  java -cp 'tools/smali3/*' com.android.tools.smali.baksmali.Main d classes.dex -o out
  java -cp 'tools/smali3/*' com.android.tools.smali.smali.Main a -a 29 -o classes.dex out
Assemble with -a 29: it writes dex 039 (as shipped) and keeps the hidden-API flags; -a 28 drops them and
-a 35 writes a dex 041 container.
Licences: smali (BSD-3), guava and jcommander (Apache-2.0), antlr/antlr-runtime/stringtemplate (BSD).
