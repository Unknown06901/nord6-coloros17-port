.class public Lcom/android/settings/portmisc/AppPref;
.super Lcom/oplus/settings/widget/preference/SettingSwitchPreference;
.source "AppPref.java"

# One row on the Choose apps page. Rows start with a transparent 40dp placeholder icon (keeps the icon space);
# the real icon is loaded the first time the row is bound (scrolled into view) and put straight into the row's
# ImageView, so listing every system app doesn't load ~450 icons up front. (Preference.setIcon here would ask the
# RecyclerView to rebind while it lays out, which throws.) match = "label\npackage" in lower case.


# instance fields
.field public info:Landroid/content/pm/ApplicationInfo;

.field public match:Ljava/lang/String;

.field private ic:Landroid/graphics/drawable/Drawable;


.method public constructor <init>(Landroid/content/Context;)V
    .registers 2

    invoke-direct {p0, p1}, Lcom/oplus/settings/widget/preference/SettingSwitchPreference;-><init>(Landroid/content/Context;)V

    return-void
.end method

.method public onBindViewHolder(Landroidx/preference/PreferenceViewHolder;)V
    .registers 5

    invoke-super {p0, p1}, Lcom/oplus/settings/widget/preference/SettingSwitchPreference;->onBindViewHolder(Landroidx/preference/PreferenceViewHolder;)V

    iget-object v0, p0, Lcom/android/settings/portmisc/AppPref;->ic:Landroid/graphics/drawable/Drawable;

    if-nez v0, :cond_have

    iget-object v2, p0, Lcom/android/settings/portmisc/AppPref;->info:Landroid/content/pm/ApplicationInfo;

    if-nez v2, :cond_load

    return-void

    :cond_load
    invoke-virtual {p0}, Landroidx/preference/Preference;->getContext()Landroid/content/Context;

    move-result-object v0

    invoke-virtual {v0}, Landroid/content/Context;->getPackageManager()Landroid/content/pm/PackageManager;

    move-result-object v1

    invoke-virtual {v2, v1}, Landroid/content/pm/ApplicationInfo;->loadIcon(Landroid/content/pm/PackageManager;)Landroid/graphics/drawable/Drawable;

    move-result-object v1

    invoke-static {v0, v1}, Lcom/android/settings/portmisc/AppsFragment;->icon(Landroid/content/Context;Landroid/graphics/drawable/Drawable;)Landroid/graphics/drawable/Drawable;

    move-result-object v0

    iput-object v0, p0, Lcom/android/settings/portmisc/AppPref;->ic:Landroid/graphics/drawable/Drawable;

    :cond_have
    const v1, 0x1020006

    invoke-virtual {p1, v1}, Landroidx/preference/PreferenceViewHolder;->findViewById(I)Landroid/view/View;

    move-result-object v1

    instance-of v2, v1, Landroid/widget/ImageView;

    if-eqz v2, :cond_end

    check-cast v1, Landroid/widget/ImageView;

    invoke-virtual {v1, v0}, Landroid/widget/ImageView;->setImageDrawable(Landroid/graphics/drawable/Drawable;)V

    :cond_end
    return-void
.end method
