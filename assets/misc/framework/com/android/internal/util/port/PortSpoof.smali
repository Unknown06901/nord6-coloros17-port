.class public final Lcom/android/internal/util/port/PortSpoof;
.super Ljava/lang/Object;
.source "PortSpoof.java"

# Added to framework.jar by lib/misc.py (patch_framework), as its own dex. Called from
#   Instrumentation.newApplication (both overloads)  -> onNewApplication(context)
#   SurfaceView.setSecure(boolean)                    -> secureVideoAllowed()
#   ApplicationPackageManager.hasSystemFeature(String, int) -> hideFeature(name)
# The switches are persist.sys.port.* properties labelled exported_system_prop (system_ext_property_contexts),
# so app processes can read them and Settings (system_app) can set them.


.method public static secureVideoAllowed()Z
    .registers 2

    const-string v0, "persist.sys.port.secure_video"

    const/4 v1, 0x0

    invoke-static {v0, v1}, Landroid/os/SystemProperties;->getBoolean(Ljava/lang/String;Z)Z

    move-result v0

    return v0
.end method


# Snapchat sees a Pixel XL (same Build values as Lunaris AOSP PixelPropsUtils.sPixelXLProps).
.method public static onNewApplication(Landroid/content/Context;)V
    .registers 4

    if-eqz p0, :done

    :try_start
    invoke-virtual {p0}, Landroid/content/Context;->getPackageName()Ljava/lang/String;

    move-result-object v0

    const-string v1, "com.snapchat.android"

    invoke-virtual {v1, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :done

    const-string v1, "persist.sys.port.spoof_snapchat"

    const/4 v2, 0x0

    invoke-static {v1, v2}, Landroid/os/SystemProperties;->getBoolean(Ljava/lang/String;Z)Z

    move-result v1

    if-eqz v1, :done

    const-string v0, "BRAND"
    const-string v1, "google"
    invoke-static {v0, v1}, Lcom/android/internal/util/port/PortSpoof;->set(Ljava/lang/String;Ljava/lang/String;)V

    const-string v0, "MANUFACTURER"
    const-string v1, "Google"
    invoke-static {v0, v1}, Lcom/android/internal/util/port/PortSpoof;->set(Ljava/lang/String;Ljava/lang/String;)V

    const-string v0, "DEVICE"
    const-string v1, "marlin"
    invoke-static {v0, v1}, Lcom/android/internal/util/port/PortSpoof;->set(Ljava/lang/String;Ljava/lang/String;)V

    const-string v0, "PRODUCT"
    invoke-static {v0, v1}, Lcom/android/internal/util/port/PortSpoof;->set(Ljava/lang/String;Ljava/lang/String;)V

    const-string v0, "HARDWARE"
    invoke-static {v0, v1}, Lcom/android/internal/util/port/PortSpoof;->set(Ljava/lang/String;Ljava/lang/String;)V

    const-string v0, "ID"
    const-string v1, "QP1A.191005.007.A3"
    invoke-static {v0, v1}, Lcom/android/internal/util/port/PortSpoof;->set(Ljava/lang/String;Ljava/lang/String;)V

    const-string v0, "MODEL"
    const-string v1, "Pixel XL"
    invoke-static {v0, v1}, Lcom/android/internal/util/port/PortSpoof;->set(Ljava/lang/String;Ljava/lang/String;)V

    const-string v0, "FINGERPRINT"
    const-string v1, "google/marlin/marlin:10/QP1A.191005.007.A3/5972272:user/release-keys"
    invoke-static {v0, v1}, Lcom/android/internal/util/port/PortSpoof;->set(Ljava/lang/String;Ljava/lang/String;)V
    :try_end
    .catchall {:try_start .. :try_end} :done

    :done
    return-void
.end method


# Google Photos asks hasSystemFeature for its NEXUS/PIXEL/PIXEL_2016_PRELOAD features (port_photos_unlimited.xml);
# ApplicationPackageManager.hasSystemFeature answers false for them while the switch is off.
.method public static hideFeature(Ljava/lang/String;)Z
    .registers 3

    const/4 v0, 0x0

    if-eqz p0, :keep

    const-string v1, "com.google.android.apps.photos."

    invoke-virtual {p0, v1}, Ljava/lang/String;->startsWith(Ljava/lang/String;)Z

    move-result v1

    if-eqz v1, :keep

    const-string v0, "persist.sys.port.photos_unlimited"

    const/4 v1, 0x1

    invoke-static {v0, v1}, Landroid/os/SystemProperties;->getBoolean(Ljava/lang/String;Z)Z

    move-result v0

    xor-int/lit8 v0, v0, 0x1

    :keep
    return v0
.end method


# Android 17 ART refuses Field.set on static final fields (IllegalAccessException, even after setAccessible),
# so the value goes straight into Build's static storage: Unsafe.putObject(Build.class, Field.offset, value).
.method private static set(Ljava/lang/String;Ljava/lang/String;)V
    .registers 7

    :try_start
    const-class v0, Landroid/os/Build;

    invoke-virtual {v0, p0}, Ljava/lang/Class;->getDeclaredField(Ljava/lang/String;)Ljava/lang/reflect/Field;

    move-result-object v1

    const-class v2, Ljava/lang/reflect/Field;

    const-string v3, "offset"

    invoke-virtual {v2, v3}, Ljava/lang/Class;->getDeclaredField(Ljava/lang/String;)Ljava/lang/reflect/Field;

    move-result-object v2

    const/4 v3, 0x1

    invoke-virtual {v2, v3}, Ljava/lang/reflect/Field;->setAccessible(Z)V

    invoke-virtual {v2, v1}, Ljava/lang/reflect/Field;->getInt(Ljava/lang/Object;)I

    move-result v1

    int-to-long v4, v1

    const-class v2, Lsun/misc/Unsafe;

    const-string v1, "theUnsafe"

    invoke-virtual {v2, v1}, Ljava/lang/Class;->getDeclaredField(Ljava/lang/String;)Ljava/lang/reflect/Field;

    move-result-object v2

    invoke-virtual {v2, v3}, Ljava/lang/reflect/Field;->setAccessible(Z)V

    const/4 v1, 0x0

    invoke-virtual {v2, v1}, Ljava/lang/reflect/Field;->get(Ljava/lang/Object;)Ljava/lang/Object;

    move-result-object v2

    check-cast v2, Lsun/misc/Unsafe;

    invoke-virtual {v2, v0, v4, v5, p1}, Lsun/misc/Unsafe;->putObject(Ljava/lang/Object;JLjava/lang/Object;)V
    :try_end
    .catchall {:try_start .. :try_end} :failed

    :failed
    return-void
.end method
