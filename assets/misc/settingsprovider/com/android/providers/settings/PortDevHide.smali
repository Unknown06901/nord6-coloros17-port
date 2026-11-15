.class public final Lcom/android/providers/settings/PortDevHide;
.super Ljava/lang/Object;
.source "PortDevHide.java"

# Added to SettingsProvider.apk by lib/misc.py (patch_settingsprovider). SettingsProvider.portDevHidden (injected)
# reads Global port_hide_dev ("1" = on) and port_hide_dev_pkgs (comma-separated packages) with the caller's
# identity cleared and asks shouldHide; packageValueForCallResult then answers "0" for the developer settings.


.method public static isDevSetting(Ljava/lang/String;)Z
    .registers 3

    const/4 v0, 0x0

    if-eqz p0, :no

    const-string v1, "development_settings_enabled"

    invoke-virtual {v1, p0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-nez v1, :yes

    const-string v1, "adb_enabled"

    invoke-virtual {v1, p0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-nez v1, :yes

    const-string v1, "adb_wifi_enabled"

    invoke-virtual {v1, p0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :no

    :yes
    const/4 v0, 0x1

    :no
    return v0
.end method


.method private static val(Lcom/android/providers/settings/SettingsState$Setting;)Ljava/lang/String;
    .registers 2

    if-eqz p0, :none

    invoke-virtual {p0}, Lcom/android/providers/settings/SettingsState$Setting;->isNull()Z

    move-result v0

    if-nez v0, :none

    invoke-virtual {p0}, Lcom/android/providers/settings/SettingsState$Setting;->getValue()Ljava/lang/String;

    move-result-object v0

    if-eqz v0, :none

    return-object v0

    :none
    const-string v0, ""

    return-object v0
.end method


# uid = the calling app; master/list = the two Global settings.
.method public static shouldHide(Landroid/content/Context;ILcom/android/providers/settings/SettingsState$Setting;Lcom/android/providers/settings/SettingsState$Setting;)Z
    .registers 12

    const/4 v0, 0x0

    invoke-static {p1}, Landroid/os/UserHandle;->getAppId(I)I

    move-result v1

    const/16 v2, 0x2710

    if-lt v1, v2, :no

    invoke-static {p2}, Lcom/android/providers/settings/PortDevHide;->val(Lcom/android/providers/settings/SettingsState$Setting;)Ljava/lang/String;

    move-result-object v1

    const-string v2, "1"

    invoke-virtual {v2, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :no

    invoke-static {p3}, Lcom/android/providers/settings/PortDevHide;->val(Lcom/android/providers/settings/SettingsState$Setting;)Ljava/lang/String;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/String;->isEmpty()Z

    move-result v2

    if-nez v2, :no

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const-string v3, ","

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    if-eqz p0, :no

    invoke-virtual {p0}, Landroid/content/Context;->getPackageManager()Landroid/content/pm/PackageManager;

    move-result-object v2

    invoke-virtual {v2, p1}, Landroid/content/pm/PackageManager;->getPackagesForUid(I)[Ljava/lang/String;

    move-result-object v2

    if-eqz v2, :no

    array-length v4, v2

    const/4 v5, 0x0

    :loop
    if-ge v5, v4, :no

    aget-object v6, v2, v5

    new-instance v7, Ljava/lang/StringBuilder;

    invoke-direct {v7}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {v7, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v7, v6}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v7, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v7}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v6

    invoke-virtual {v1, v6}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v6

    if-nez v6, :yes

    add-int/lit8 v5, v5, 0x1

    goto :loop

    :yes
    const/4 v0, 0x1

    :no
    return v0
.end method
