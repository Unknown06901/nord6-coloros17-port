.class public Lcom/android/settings/portmisc/AppsFragment;
.super Lcom/android/settings/SettingsPreferenceFragment;
.source "AppsFragment.java"

# interfaces
.implements Landroidx/preference/Preference$OnPreferenceChangeListener;
.implements Landroid/view/View$OnClickListener;
.implements Landroid/text/TextWatcher;

# Settings > Miscellaneous > Choose apps (hide developer options). One switch per user-installed app; the ticked
# packages go to Global port_hide_dev_pkgs (comma-separated), which the patched SettingsProvider reads.
# Search: a COUISearchBar pill (as on the Settings home page) is the first row; a tap switches it to editing,
# Cancel or Back (PortSearchBack) clears it. It matches label or package. The overflow menu has "Show system apps" /
# "Hide system apps" (the ColorOS popup draws no checkmarks, so the title says what a tap does). Labels are loaded once per fill and sorted through
# a TreeMap; icons load when a row is first shown (AppPref).


# instance fields
.field private cat:Landroidx/preference/PreferenceGroup;

.field private sys:Z

.field private query:Ljava/lang/String;

.field bar:Lcom/coui/appcompat/searchview/COUISearchBar;

.field private back:Lcom/android/settings/portmisc/PortSearchBack;


.method public constructor <init>()V
    .registers 1

    invoke-direct {p0}, Lcom/android/settings/SettingsPreferenceFragment;-><init>()V

    return-void
.end method

.method private list()Ljava/lang/String;
    .registers 3

    invoke-virtual {p0}, Lcom/android/settings/SettingsPreferenceFragment;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    const-string v1, "port_hide_dev_pkgs"

    invoke-static {v0, v1}, Landroid/provider/Settings$Global;->getString(Landroid/content/ContentResolver;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    if-nez v0, :cond_ok

    const-string v0, ""

    :cond_ok
    return-object v0
.end method

# Every app icon drawn at 40dp, so apps with oversized adaptive icons don't stretch their row.
.method static icon(Landroid/content/Context;Landroid/graphics/drawable/Drawable;)Landroid/graphics/drawable/Drawable;
    .registers 7

    if-nez p1, :cond_has

    return-object p1

    :cond_has
    invoke-virtual {p0}, Landroid/content/Context;->getResources()Landroid/content/res/Resources;

    move-result-object v0

    invoke-virtual {v0}, Landroid/content/res/Resources;->getDisplayMetrics()Landroid/util/DisplayMetrics;

    move-result-object v1

    iget v1, v1, Landroid/util/DisplayMetrics;->density:F

    const/high16 v2, 0x42200000    # 40.0f

    mul-float/2addr v1, v2

    float-to-int v1, v1

    sget-object v2, Landroid/graphics/Bitmap$Config;->ARGB_8888:Landroid/graphics/Bitmap$Config;

    invoke-static {v1, v1, v2}, Landroid/graphics/Bitmap;->createBitmap(IILandroid/graphics/Bitmap$Config;)Landroid/graphics/Bitmap;

    move-result-object v2

    new-instance v3, Landroid/graphics/Canvas;

    invoke-direct {v3, v2}, Landroid/graphics/Canvas;-><init>(Landroid/graphics/Bitmap;)V

    const/4 v4, 0x0

    invoke-virtual {p1, v4, v4, v1, v1}, Landroid/graphics/drawable/Drawable;->setBounds(IIII)V

    invoke-virtual {p1, v3}, Landroid/graphics/drawable/Drawable;->draw(Landroid/graphics/Canvas;)V

    new-instance v5, Landroid/graphics/drawable/BitmapDrawable;

    invoke-direct {v5, v0, v2}, Landroid/graphics/drawable/BitmapDrawable;-><init>(Landroid/content/res/Resources;Landroid/graphics/Bitmap;)V

    return-object v5
.end method

# (Re)builds the rows: user-installed apps, plus system apps while sys is set; then applies the search.
.method private fill()V
    .registers 15

    iget-object v0, p0, Lcom/android/settings/portmisc/AppsFragment;->cat:Landroidx/preference/PreferenceGroup;

    if-nez v0, :cond_cat

    return-void

    :cond_cat
    invoke-virtual {v0}, Landroidx/preference/PreferenceGroup;->removeAll()V

    invoke-virtual {p0}, Lcom/android/settings/core/InstrumentedPreferenceFragment;->getPrefContext()Landroid/content/Context;

    move-result-object v1

    iget-boolean v2, p0, Lcom/android/settings/portmisc/AppsFragment;->sys:Z

    new-instance v3, Ljava/lang/StringBuilder;

    invoke-direct {v3}, Ljava/lang/StringBuilder;-><init>()V

    const-string v4, ","

    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-direct {p0}, Lcom/android/settings/portmisc/AppsFragment;->list()Ljava/lang/String;

    move-result-object v5

    invoke-virtual {v3, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v1}, Landroid/content/Context;->getPackageManager()Landroid/content/pm/PackageManager;

    move-result-object v5

    const/4 v6, 0x0

    invoke-virtual {v5, v6}, Landroid/content/pm/PackageManager;->getInstalledApplications(I)Ljava/util/List;

    move-result-object v6

    invoke-interface {v6}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v6

    new-instance v12, Ljava/util/TreeMap;

    invoke-direct {v12}, Ljava/util/TreeMap;-><init>()V

    new-instance v13, Landroid/graphics/drawable/ColorDrawable;

    const/4 v7, 0x0

    invoke-direct {v13, v7}, Landroid/graphics/drawable/ColorDrawable;-><init>(I)V

    invoke-static {v1, v13}, Lcom/android/settings/portmisc/AppsFragment;->icon(Landroid/content/Context;Landroid/graphics/drawable/Drawable;)Landroid/graphics/drawable/Drawable;

    move-result-object v13

    :goto_loop
    invoke-interface {v6}, Ljava/util/Iterator;->hasNext()Z

    move-result v7

    if-eqz v7, :cond_done

    invoke-interface {v6}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v7

    check-cast v7, Landroid/content/pm/ApplicationInfo;

    if-nez v2, :cond_show

    iget v8, v7, Landroid/content/pm/ApplicationInfo;->flags:I

    and-int/lit8 v8, v8, 0x1

    if-nez v8, :goto_loop

    :cond_show
    iget-object v8, v7, Landroid/content/pm/ApplicationInfo;->packageName:Ljava/lang/String;

    new-instance v9, Lcom/android/settings/portmisc/AppPref;

    invoke-direct {v9, v1}, Lcom/android/settings/portmisc/AppPref;-><init>(Landroid/content/Context;)V

    iput-object v7, v9, Lcom/android/settings/portmisc/AppPref;->info:Landroid/content/pm/ApplicationInfo;

    invoke-virtual {v9, v8}, Landroidx/preference/Preference;->setKey(Ljava/lang/String;)V

    const/4 v10, 0x0

    invoke-virtual {v9, v10}, Landroidx/preference/Preference;->setPersistent(Z)V

    invoke-virtual {v7, v5}, Landroid/content/pm/ApplicationInfo;->loadLabel(Landroid/content/pm/PackageManager;)Ljava/lang/CharSequence;

    move-result-object v10

    invoke-virtual {v9, v10}, Landroidx/preference/Preference;->setTitle(Ljava/lang/CharSequence;)V

    invoke-virtual {v9, v8}, Landroidx/preference/Preference;->setSummary(Ljava/lang/CharSequence;)V

    invoke-virtual {v9, v13}, Landroidx/preference/Preference;->setIcon(Landroid/graphics/drawable/Drawable;)V

    invoke-virtual {v10}, Ljava/lang/Object;->toString()Ljava/lang/String;

    move-result-object v10

    invoke-virtual {v10}, Ljava/lang/String;->toLowerCase()Ljava/lang/String;

    move-result-object v10

    new-instance v11, Ljava/lang/StringBuilder;

    invoke-direct {v11}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {v11, v10}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v10, "\n"

    invoke-virtual {v11, v10}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v8}, Ljava/lang/String;->toLowerCase()Ljava/lang/String;

    move-result-object v10

    invoke-virtual {v11, v10}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v11}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v10

    iput-object v10, v9, Lcom/android/settings/portmisc/AppPref;->match:Ljava/lang/String;

    new-instance v11, Ljava/lang/StringBuilder;

    invoke-direct {v11}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {v11, v10}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v10, "\u0000"

    invoke-virtual {v11, v10}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v11, v8}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v11}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v11

    invoke-virtual {v12, v11, v9}, Ljava/util/TreeMap;->put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;

    new-instance v10, Ljava/lang/StringBuilder;

    invoke-direct {v10}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {v10, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v10, v8}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v10, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v10}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v10

    invoke-virtual {v3, v10}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v10

    move-object v11, v9

    check-cast v11, Landroidx/preference/TwoStatePreference;

    invoke-virtual {v11, v10}, Landroidx/preference/TwoStatePreference;->setChecked(Z)V

    invoke-virtual {v9, p0}, Landroidx/preference/Preference;->setOnPreferenceChangeListener(Landroidx/preference/Preference$OnPreferenceChangeListener;)V

    goto :goto_loop

    :cond_done
    invoke-virtual {v12}, Ljava/util/TreeMap;->values()Ljava/util/Collection;

    move-result-object v6

    invoke-interface {v6}, Ljava/util/Collection;->iterator()Ljava/util/Iterator;

    move-result-object v6

    :goto_add
    invoke-interface {v6}, Ljava/util/Iterator;->hasNext()Z

    move-result v7

    if-eqz v7, :cond_end

    invoke-interface {v6}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v9

    check-cast v9, Landroidx/preference/Preference;

    invoke-virtual {v0, v9}, Landroidx/preference/PreferenceGroup;->addPreference(Landroidx/preference/Preference;)Z

    goto :goto_add

    :cond_end
    invoke-direct {p0}, Lcom/android/settings/portmisc/AppsFragment;->filter()V

    return-void
.end method

# Shows only the rows whose "label\npackage" (lower case) contains the search text.
.method private filter()V
    .registers 7

    iget-object v0, p0, Lcom/android/settings/portmisc/AppsFragment;->cat:Landroidx/preference/PreferenceGroup;

    if-nez v0, :cond_cat

    return-void

    :cond_cat
    iget-object v1, p0, Lcom/android/settings/portmisc/AppsFragment;->query:Ljava/lang/String;

    if-nez v1, :cond_q

    const-string v1, ""

    :cond_q
    invoke-virtual {v0}, Landroidx/preference/PreferenceGroup;->getPreferenceCount()I

    move-result v2

    const/4 v3, 0x0

    :goto_loop
    if-ge v3, v2, :cond_end

    invoke-virtual {v0, v3}, Landroidx/preference/PreferenceGroup;->getPreference(I)Landroidx/preference/Preference;

    move-result-object v4

    check-cast v4, Lcom/android/settings/portmisc/AppPref;

    iget-object v5, v4, Lcom/android/settings/portmisc/AppPref;->match:Ljava/lang/String;

    invoke-virtual {v5, v1}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v5

    invoke-virtual {v4, v5}, Landroidx/preference/Preference;->setVisible(Z)V

    add-int/lit8 v3, v3, 0x1

    goto :goto_loop

    :cond_end
    return-void
.end method


# virtual methods
.method public getHelpResource()I
    .registers 2

    const/4 v0, 0x0

    return v0
.end method

.method public getMetricsCategory()I
    .registers 2

    const/4 v0, 0x0

    return v0
.end method

.method public onCreate(Landroid/os/Bundle;)V
    .registers 3

    invoke-super {p0, p1}, Lcom/android/settings/SettingsPreferenceFragment;->onCreate(Landroid/os/Bundle;)V

    const/4 v0, 0x1

    invoke-virtual {p0, v0}, Landroidx/fragment/app/Fragment;->setHasOptionsMenu(Z)V

    return-void
.end method

.method public onCreatePreferences(Landroid/os/Bundle;Ljava/lang/String;)V
    .registers 7

    invoke-virtual {p0}, Lcom/android/settings/core/InstrumentedPreferenceFragment;->getPrefContext()Landroid/content/Context;

    move-result-object v0

    invoke-virtual {p0}, Landroidx/preference/PreferenceFragmentCompat;->getPreferenceManager()Landroidx/preference/PreferenceManager;

    move-result-object v1

    invoke-virtual {v1, v0}, Landroidx/preference/PreferenceManager;->createPreferenceScreen(Landroid/content/Context;)Landroidx/preference/PreferenceScreen;

    move-result-object v1

    invoke-virtual {p0, v1}, Landroidx/preference/PreferenceFragmentCompat;->setPreferenceScreen(Landroidx/preference/PreferenceScreen;)V

    invoke-direct {p0, v0, v1}, Lcom/android/settings/portmisc/AppsFragment;->addSearchBar(Landroid/content/Context;Landroidx/preference/PreferenceGroup;)V

    new-instance v2, Lcom/oplus/settings/widget/preference/SettingsPreferenceCategory;

    invoke-direct {v2, v0}, Lcom/oplus/settings/widget/preference/SettingsPreferenceCategory;-><init>(Landroid/content/Context;)V

    const-string v3, "Turned on apps see Developer options and USB debugging as off. Force stop the app after changing."

    invoke-virtual {v2, v3}, Landroidx/preference/Preference;->setTitle(Ljava/lang/CharSequence;)V

    invoke-virtual {v1, v2}, Landroidx/preference/PreferenceGroup;->addPreference(Landroidx/preference/Preference;)Z

    iput-object v2, p0, Lcom/android/settings/portmisc/AppsFragment;->cat:Landroidx/preference/PreferenceGroup;

    invoke-direct {p0}, Lcom/android/settings/portmisc/AppsFragment;->fill()V

    return-void
.end method


# The search bar: the same COUISearchBar pill as on the Settings home page, as the first row of the list.
.method private addSearchBar(Landroid/content/Context;Landroidx/preference/PreferenceGroup;)V
    .registers 7

    new-instance v0, Lcom/coui/appcompat/searchview/COUISearchBar;

    invoke-direct {v0, p1}, Lcom/coui/appcompat/searchview/COUISearchBar;-><init>(Landroid/content/Context;)V

    new-instance v1, Landroid/view/ViewGroup$LayoutParams;

    invoke-virtual {p1}, Landroid/content/Context;->getResources()Landroid/content/res/Resources;

    move-result-object v2

    invoke-virtual {v2}, Landroid/content/res/Resources;->getDisplayMetrics()Landroid/util/DisplayMetrics;

    move-result-object v2

    iget v2, v2, Landroid/util/DisplayMetrics;->density:F

    const/high16 v3, 0x42500000    # 52.0f (the Settings home search bar height)

    mul-float/2addr v3, v2

    float-to-int v3, v3

    const/4 v2, -0x1

    invoke-direct {v1, v2, v3}, Landroid/view/ViewGroup$LayoutParams;-><init>(II)V

    invoke-virtual {v0, v1}, Landroid/view/View;->setLayoutParams(Landroid/view/ViewGroup$LayoutParams;)V

    iput-object v0, p0, Lcom/android/settings/portmisc/AppsFragment;->bar:Lcom/coui/appcompat/searchview/COUISearchBar;

    invoke-virtual {v0}, Lcom/coui/appcompat/searchview/COUISearchBar;->getSearchEditText()Landroid/widget/EditText;

    move-result-object v1

    if-eqz v1, :cond_noedit

    const-string v2, "Search apps"

    invoke-virtual {v1, v2}, Landroid/widget/TextView;->setHint(Ljava/lang/CharSequence;)V

    invoke-virtual {v1, p0}, Landroid/widget/TextView;->addTextChangedListener(Landroid/text/TextWatcher;)V

    :cond_noedit
    invoke-virtual {v0, p0}, Lcom/coui/appcompat/searchview/COUISearchBar;->setOnClickListener(Landroid/view/View$OnClickListener;)V

    invoke-virtual {v0}, Lcom/coui/appcompat/searchview/COUISearchBar;->getFunctionalButton()Landroid/widget/TextView;

    move-result-object v1

    if-eqz v1, :cond_nobtn

    invoke-virtual {v1, p0}, Landroid/view/View;->setOnClickListener(Landroid/view/View$OnClickListener;)V

    :cond_nobtn
    new-instance v1, Lcom/android/settingslib/widget/LayoutPreference;

    invoke-direct {v1, p1, v0}, Lcom/android/settingslib/widget/LayoutPreference;-><init>(Landroid/content/Context;Landroid/view/View;)V

    const-string v2, "port_search"

    invoke-virtual {v1, v2}, Landroidx/preference/Preference;->setKey(Ljava/lang/String;)V

    const/4 v2, 0x0

    invoke-virtual {v1, v2}, Landroidx/preference/Preference;->setSelectable(Z)V

    invoke-virtual {p2, v1}, Landroidx/preference/PreferenceGroup;->addPreference(Landroidx/preference/Preference;)Z

    invoke-virtual {p0}, Landroidx/fragment/app/Fragment;->getActivity()Landroidx/fragment/app/FragmentActivity;

    move-result-object v1

    if-eqz v1, :cond_end

    new-instance v2, Lcom/android/settings/portmisc/PortSearchBack;

    invoke-direct {v2, p0}, Lcom/android/settings/portmisc/PortSearchBack;-><init>(Lcom/android/settings/portmisc/AppsFragment;)V

    iput-object v2, p0, Lcom/android/settings/portmisc/AppsFragment;->back:Lcom/android/settings/portmisc/PortSearchBack;

    invoke-virtual {v1}, Landroidx/activity/ComponentActivity;->getOnBackPressedDispatcher()Landroidx/activity/OnBackPressedDispatcher;

    move-result-object v1

    invoke-virtual {v1, p0, v2}, Landroidx/activity/OnBackPressedDispatcher;->addCallback(Landroidx/lifecycle/LifecycleOwner;Landroidx/activity/OnBackPressedCallback;)V

    :cond_end
    return-void
.end method

# Overflow menu: "Show system apps" / "Hide system apps".
.method public onCreateOptionsMenu(Landroid/view/Menu;Landroid/view/MenuInflater;)V
    .registers 8

    invoke-super {p0, p1, p2}, Lcom/android/settings/SettingsPreferenceFragment;->onCreateOptionsMenu(Landroid/view/Menu;Landroid/view/MenuInflater;)V

    const/4 v0, 0x0

    const/4 v1, 0x2

    const/16 v2, 0x64

    const-string v4, "Show system apps"

    iget-boolean v3, p0, Lcom/android/settings/portmisc/AppsFragment;->sys:Z

    if-eqz v3, :cond_title

    const-string v4, "Hide system apps"

    :cond_title
    invoke-interface {p1, v0, v1, v2, v4}, Landroid/view/Menu;->add(IIILjava/lang/CharSequence;)Landroid/view/MenuItem;

    move-result-object v3

    invoke-interface {v3, v0}, Landroid/view/MenuItem;->setShowAsAction(I)V

    return-void
.end method


# Tap on the bar (normal state) switches it to editing; tap on its Cancel button closes the search. COUISearchBar
# hands its click listener to its inner background view, so anything but the Cancel button counts as the bar.
.method public onClick(Landroid/view/View;)V
    .registers 4

    iget-object v0, p0, Lcom/android/settings/portmisc/AppsFragment;->bar:Lcom/coui/appcompat/searchview/COUISearchBar;

    if-nez v0, :cond_bar

    return-void

    :cond_bar
    invoke-virtual {v0}, Lcom/coui/appcompat/searchview/COUISearchBar;->getFunctionalButton()Landroid/widget/TextView;

    move-result-object v1

    if-eq p1, v1, :cond_btn

    invoke-virtual {v0}, Lcom/coui/appcompat/searchview/COUISearchBar;->getSearchState()I

    move-result v1

    if-nez v1, :cond_end

    const/4 v1, 0x1

    invoke-virtual {v0, v1}, Lcom/coui/appcompat/searchview/COUISearchBar;->changeStateWithAnimation(I)V

    iget-object v0, p0, Lcom/android/settings/portmisc/AppsFragment;->back:Lcom/android/settings/portmisc/PortSearchBack;

    if-eqz v0, :cond_end

    invoke-virtual {v0, v1}, Landroidx/activity/OnBackPressedCallback;->setEnabled(Z)V

    :cond_end
    return-void

    :cond_btn
    invoke-virtual {p0}, Lcom/android/settings/portmisc/AppsFragment;->closeSearch()Z

    return-void
.end method

# Clears the text and returns the bar to its normal state. Returns false when the search wasn't open.
.method public closeSearch()Z
    .registers 4

    iget-object v0, p0, Lcom/android/settings/portmisc/AppsFragment;->bar:Lcom/coui/appcompat/searchview/COUISearchBar;

    const/4 v1, 0x0

    if-nez v0, :cond_bar

    return v1

    :cond_bar
    invoke-virtual {v0}, Lcom/coui/appcompat/searchview/COUISearchBar;->getSearchState()I

    move-result v2

    if-nez v2, :cond_open

    return v1

    :cond_open
    invoke-virtual {v0}, Lcom/coui/appcompat/searchview/COUISearchBar;->getSearchEditText()Landroid/widget/EditText;

    move-result-object v1

    if-eqz v1, :cond_hide

    const-string v2, ""

    invoke-virtual {v1, v2}, Landroid/widget/TextView;->setText(Ljava/lang/CharSequence;)V

    :cond_hide
    const/4 v1, 0x0

    invoke-virtual {v0, v1}, Lcom/coui/appcompat/searchview/COUISearchBar;->changeStateWithAnimation(I)V

    iget-object v2, p0, Lcom/android/settings/portmisc/AppsFragment;->back:Lcom/android/settings/portmisc/PortSearchBack;

    if-eqz v2, :cond_noback

    invoke-virtual {v2, v1}, Landroidx/activity/OnBackPressedCallback;->setEnabled(Z)V

    :cond_noback

    const/4 v1, 0x1

    return v1
.end method

.method public afterTextChanged(Landroid/text/Editable;)V
    .registers 3

    invoke-virtual {p1}, Ljava/lang/Object;->toString()Ljava/lang/String;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/String;->toLowerCase()Ljava/lang/String;

    move-result-object v0

    iput-object v0, p0, Lcom/android/settings/portmisc/AppsFragment;->query:Ljava/lang/String;

    invoke-direct {p0}, Lcom/android/settings/portmisc/AppsFragment;->filter()V

    return-void
.end method

.method public beforeTextChanged(Ljava/lang/CharSequence;III)V
    .registers 5

    return-void
.end method

.method public onTextChanged(Ljava/lang/CharSequence;III)V
    .registers 5

    return-void
.end method

.method public onOptionsItemSelected(Landroid/view/MenuItem;)Z
    .registers 4

    invoke-interface {p1}, Landroid/view/MenuItem;->getItemId()I

    move-result v0

    const/4 v1, 0x2

    if-ne v0, v1, :cond_super

    iget-boolean v0, p0, Lcom/android/settings/portmisc/AppsFragment;->sys:Z

    xor-int/lit8 v0, v0, 0x1

    iput-boolean v0, p0, Lcom/android/settings/portmisc/AppsFragment;->sys:Z

    const-string v1, "Show system apps"

    if-eqz v0, :cond_title

    const-string v1, "Hide system apps"

    :cond_title
    invoke-interface {p1, v1}, Landroid/view/MenuItem;->setTitle(Ljava/lang/CharSequence;)Landroid/view/MenuItem;

    invoke-direct {p0}, Lcom/android/settings/portmisc/AppsFragment;->fill()V

    const/4 v0, 0x1

    return v0

    :cond_super
    invoke-super {p0, p1}, Lcom/android/settings/SettingsPreferenceFragment;->onOptionsItemSelected(Landroid/view/MenuItem;)Z

    move-result v0

    return v0
.end method



.method public onResume()V
    .registers 3

    invoke-super {p0}, Lcom/android/settings/SettingsPreferenceFragment;->onResume()V

    invoke-virtual {p0}, Landroidx/fragment/app/Fragment;->getActivity()Landroidx/fragment/app/FragmentActivity;

    move-result-object v0

    if-eqz v0, :cond_end

    const-string v1, "Choose apps"

    invoke-virtual {v0, v1}, Landroid/app/Activity;->setTitle(Ljava/lang/CharSequence;)V

    :cond_end
    return-void
.end method

.method public onPreferenceChange(Landroidx/preference/Preference;Ljava/lang/Object;)Z
    .registers 10

    invoke-virtual {p1}, Landroidx/preference/Preference;->getKey()Ljava/lang/String;

    move-result-object v0

    instance-of v1, p2, Ljava/lang/Boolean;

    if-eqz v1, :cond_reject

    if-eqz v0, :cond_reject

    move-object v1, p2

    check-cast v1, Ljava/lang/Boolean;

    invoke-virtual {v1}, Ljava/lang/Boolean;->booleanValue()Z

    move-result v1



    new-instance v2, Ljava/util/ArrayList;

    invoke-direct {v2}, Ljava/util/ArrayList;-><init>()V

    invoke-direct {p0}, Lcom/android/settings/portmisc/AppsFragment;->list()Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v3}, Ljava/lang/String;->isEmpty()Z

    move-result v4

    if-nez v4, :cond_empty

    const-string v4, ","

    invoke-virtual {v3, v4}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    move-result-object v3

    invoke-static {v3}, Ljava/util/Arrays;->asList([Ljava/lang/Object;)Ljava/util/List;

    move-result-object v3

    invoke-virtual {v2, v3}, Ljava/util/ArrayList;->addAll(Ljava/util/Collection;)Z

    :cond_empty
    invoke-virtual {v2, v0}, Ljava/util/ArrayList;->remove(Ljava/lang/Object;)Z

    if-eqz v1, :cond_off

    invoke-virtual {v2, v0}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z

    :cond_off
    const-string v3, ","

    invoke-static {v3, v2}, Ljava/lang/String;->join(Ljava/lang/CharSequence;Ljava/lang/Iterable;)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {p0}, Lcom/android/settings/SettingsPreferenceFragment;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v4

    const-string v5, "port_hide_dev_pkgs"

    invoke-static {v4, v5, v3}, Landroid/provider/Settings$Global;->putString(Landroid/content/ContentResolver;Ljava/lang/String;Ljava/lang/String;)Z

    const/4 v1, 0x1

    return v1

    :cond_reject
    const/4 v1, 0x0

    return v1
.end method

.method public onPreferenceClickedDcs(Landroidx/preference/Preference;)V
    .registers 2

    return-void
.end method
