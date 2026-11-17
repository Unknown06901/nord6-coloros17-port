.class public Lcom/android/settings/portmisc/AnimScale;
.super Ljava/lang/Object;
.source "AnimScale.java"

# Developer options > Window / Transition / Animator duration scale. The three stock controllers hand
# updateState() and onPreferenceChange() to this class (see misc.anim_scale_smali). It drops the
# list entries below 0.5x ("Animation off" = 0x hangs SystemUI on this port), appends a "Custom…"
# entry that opens a number box, and refuses anything outside 0.5x..10x.

.field static final CUSTOM:Ljava/lang/String; = "custom"


.method public constructor <init>()V
    .registers 1

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

# 0 window, 1 transition, 2 animator duration (IWindowManager scale index)
.method static which(Landroidx/preference/Preference;)I
    .registers 3

    invoke-virtual {p0}, Landroidx/preference/Preference;->getKey()Ljava/lang/String;

    move-result-object v0

    const-string v1, "transition_animation_scale"

    invoke-virtual {v1, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_not_t

    const/4 v0, 0x1

    return v0

    :cond_not_t
    const-string v1, "animator_duration_scale"

    invoke-virtual {v1, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_not_a

    const/4 v0, 0x2

    return v0

    :cond_not_a
    const/4 v0, 0x0

    return v0
.end method

.method static wm()Landroid/view/IWindowManager;
    .registers 1

    const-string v0, "window"

    invoke-static {v0}, Landroid/os/ServiceManager;->getService(Ljava/lang/String;)Landroid/os/IBinder;

    move-result-object v0

    invoke-static {v0}, Landroid/view/IWindowManager$Stub;->asInterface(Landroid/os/IBinder;)Landroid/view/IWindowManager;

    move-result-object v0

    return-object v0
.end method

.method static get(I)F
    .registers 2

    :try_start
    invoke-static {}, Lcom/android/settings/portmisc/AnimScale;->wm()Landroid/view/IWindowManager;

    move-result-object v0

    invoke-interface {v0, p0}, Landroid/view/IWindowManager;->getAnimationScale(I)F

    move-result v0
    :try_end
    .catch Ljava/lang/Exception; {:try_start .. :try_end} :catch

    return v0

    :catch
    const/high16 v0, 0x3f800000    # 1.0f

    return v0
.end method

.method static set(IF)V
    .registers 3

    :try_start
    invoke-static {}, Lcom/android/settings/portmisc/AnimScale;->wm()Landroid/view/IWindowManager;

    move-result-object v0

    invoke-interface {v0, p0, p1}, Landroid/view/IWindowManager;->setAnimationScale(IF)V
    :try_end
    .catch Ljava/lang/Exception; {:try_start .. :try_end} :catch

    :catch
    return-void
.end method

# float value of a list entry / typed text, -1 when it isn't a number
.method static parse(Ljava/lang/CharSequence;)F
    .registers 2

    :try_start
    invoke-interface {p0}, Ljava/lang/CharSequence;->toString()Ljava/lang/String;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object v0

    invoke-static {v0}, Ljava/lang/Float;->parseFloat(Ljava/lang/String;)F

    move-result v0
    :try_end
    .catch Ljava/lang/Exception; {:try_start .. :try_end} :catch

    return v0

    :catch
    const/high16 v0, -0x40800000    # -1.0f

    return v0
.end method

# true when 0.5 <= v <= 10 (NaN fails both compares)
.method static ok(F)Z
    .registers 3

    const/high16 v0, 0x3f000000    # 0.5f

    cmpl-float v0, p0, v0

    if-ltz v0, :cond_bad

    const/high16 v0, 0x41200000    # 10.0f

    cmpg-float v0, p0, v0

    if-gtz v0, :cond_bad

    const/4 v0, 0x1

    return v0

    :cond_bad
    const/4 v0, 0x0

    return v0
.end method

# Called from the controller's updateState(): trim the list once, then show the live scale.
.method public static refresh(Landroidx/preference/Preference;)V
    .registers 12

    instance-of v0, p0, Landroidx/preference/ListPreference;

    if-nez v0, :cond_list

    return-void

    :cond_list
    move-object v10, p0

    check-cast v10, Landroidx/preference/ListPreference;

    invoke-virtual {v10}, Landroidx/preference/ListPreference;->getEntryValues()[Ljava/lang/CharSequence;

    move-result-object v0

    invoke-virtual {v10}, Landroidx/preference/ListPreference;->getEntries()[Ljava/lang/CharSequence;

    move-result-object v1

    if-eqz v0, :cond_ret

    if-eqz v1, :cond_ret

    array-length v2, v0

    if-eqz v2, :cond_ret

    array-length v3, v1

    if-ne v3, v2, :cond_ret

    add-int/lit8 v3, v2, -0x1

    aget-object v3, v0, v3

    const-string v4, "custom"

    invoke-virtual {v4, v3}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-nez v3, :cond_trimmed

    new-instance v5, Ljava/util/ArrayList;

    invoke-direct {v5}, Ljava/util/ArrayList;-><init>()V

    new-instance v6, Ljava/util/ArrayList;

    invoke-direct {v6}, Ljava/util/ArrayList;-><init>()V

    const/4 v3, 0x0

    :goto_trim
    if-ge v3, v2, :cond_trim_done

    aget-object v7, v0, v3

    invoke-static {v7}, Lcom/android/settings/portmisc/AnimScale;->parse(Ljava/lang/CharSequence;)F

    move-result v8

    invoke-static {v8}, Lcom/android/settings/portmisc/AnimScale;->ok(F)Z

    move-result v8

    if-eqz v8, :cond_skip

    invoke-virtual {v6, v7}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z

    aget-object v7, v1, v3

    invoke-virtual {v5, v7}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z

    :cond_skip
    add-int/lit8 v3, v3, 0x1

    goto :goto_trim

    :cond_trim_done
    const-string v7, "Custom…"

    invoke-virtual {v5, v7}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z

    invoke-virtual {v6, v4}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z

    invoke-virtual {v5}, Ljava/util/ArrayList;->size()I

    move-result v3

    new-array v7, v3, [Ljava/lang/CharSequence;

    invoke-virtual {v5, v7}, Ljava/util/ArrayList;->toArray([Ljava/lang/Object;)[Ljava/lang/Object;

    move-result-object v7

    check-cast v7, [Ljava/lang/CharSequence;

    invoke-virtual {v10, v7}, Landroidx/preference/ListPreference;->setEntries([Ljava/lang/CharSequence;)V

    new-array v7, v3, [Ljava/lang/CharSequence;

    invoke-virtual {v6, v7}, Ljava/util/ArrayList;->toArray([Ljava/lang/Object;)[Ljava/lang/Object;

    move-result-object v7

    check-cast v7, [Ljava/lang/CharSequence;

    invoke-virtual {v10, v7}, Landroidx/preference/ListPreference;->setEntryValues([Ljava/lang/CharSequence;)V

    invoke-virtual {v10}, Landroidx/preference/ListPreference;->getEntryValues()[Ljava/lang/CharSequence;

    move-result-object v0

    invoke-virtual {v10}, Landroidx/preference/ListPreference;->getEntries()[Ljava/lang/CharSequence;

    move-result-object v1

    array-length v2, v0

    :cond_trimmed
    invoke-static {v10}, Lcom/android/settings/portmisc/AnimScale;->which(Landroidx/preference/Preference;)I

    move-result v3

    invoke-static {v3}, Lcom/android/settings/portmisc/AnimScale;->get(I)F

    move-result v4

    const/4 v5, 0x0

    add-int/lit8 v6, v2, -0x1

    :goto_find
    if-ge v5, v6, :cond_custom

    aget-object v7, v0, v5

    invoke-static {v7}, Lcom/android/settings/portmisc/AnimScale;->parse(Ljava/lang/CharSequence;)F

    move-result v8

    sub-float v8, v8, v4

    invoke-static {v8}, Ljava/lang/Math;->abs(F)F

    move-result v8

    const v9, 0x3a83126f    # 0.001f

    cmpg-float v8, v8, v9

    if-gez v8, :cond_next

    invoke-interface {v7}, Ljava/lang/CharSequence;->toString()Ljava/lang/String;

    move-result-object v7

    invoke-virtual {v10, v7}, Landroidx/preference/ListPreference;->setValue(Ljava/lang/String;)V

    aget-object v7, v1, v5

    invoke-virtual {v10, v7}, Landroidx/preference/Preference;->setSummary(Ljava/lang/CharSequence;)V

    return-void

    :cond_next
    add-int/lit8 v5, v5, 0x1

    goto :goto_find

    :cond_custom
    const-string v7, "custom"

    invoke-virtual {v10, v7}, Landroidx/preference/ListPreference;->setValue(Ljava/lang/String;)V

    new-instance v7, Ljava/lang/StringBuilder;

    const-string v8, "Custom ("

    invoke-direct {v7, v8}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v7, v4}, Ljava/lang/StringBuilder;->append(F)Ljava/lang/StringBuilder;

    const-string v8, "x)"

    invoke-virtual {v7, v8}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v7}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v7

    invoke-virtual {v10, v7}, Landroidx/preference/Preference;->setSummary(Ljava/lang/CharSequence;)V

    :cond_ret
    return-void
.end method

# Called from the controller's onPreferenceChange(). Always false: refresh() sets the shown value.
.method public static onChange(Landroidx/preference/Preference;Ljava/lang/Object;)Z
    .registers 5

    invoke-static {p0}, Lcom/android/settings/portmisc/AnimScale;->which(Landroidx/preference/Preference;)I

    move-result v0

    if-eqz p1, :cond_ret

    invoke-virtual {p1}, Ljava/lang/Object;->toString()Ljava/lang/String;

    move-result-object v1

    const-string v2, "custom"

    invoke-virtual {v2, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v2

    if-eqz v2, :cond_value

    invoke-static {p0, v0}, Lcom/android/settings/portmisc/AnimScale;->dialog(Landroidx/preference/Preference;I)V

    goto :cond_ret

    :cond_value
    invoke-static {v1}, Lcom/android/settings/portmisc/AnimScale;->parse(Ljava/lang/CharSequence;)F

    move-result v1

    invoke-static {v1}, Lcom/android/settings/portmisc/AnimScale;->ok(F)Z

    move-result v2

    if-eqz v2, :cond_ret

    invoke-static {v0, v1}, Lcom/android/settings/portmisc/AnimScale;->set(IF)V

    invoke-static {p0}, Lcom/android/settings/portmisc/AnimScale;->refresh(Landroidx/preference/Preference;)V

    :cond_ret
    const/4 v0, 0x0

    return v0
.end method

.method static dialog(Landroidx/preference/Preference;I)V
    .registers 9

    invoke-virtual {p0}, Landroidx/preference/Preference;->getContext()Landroid/content/Context;

    move-result-object v0

    new-instance v1, Landroid/widget/EditText;

    invoke-direct {v1, v0}, Landroid/widget/EditText;-><init>(Landroid/content/Context;)V

    const/16 v2, 0x2002    # TYPE_CLASS_NUMBER | TYPE_NUMBER_FLAG_DECIMAL

    invoke-virtual {v1, v2}, Landroid/widget/EditText;->setInputType(I)V

    const/4 v2, 0x1

    invoke-virtual {v1, v2}, Landroid/widget/EditText;->setSingleLine(Z)V

    const-string v2, "0.5 – 10"

    invoke-virtual {v1, v2}, Landroid/widget/EditText;->setHint(Ljava/lang/CharSequence;)V

    invoke-static {p1}, Lcom/android/settings/portmisc/AnimScale;->get(I)F

    move-result v2

    invoke-static {v2}, Ljava/lang/String;->valueOf(F)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v1, v2}, Landroid/widget/EditText;->setText(Ljava/lang/CharSequence;)V

    invoke-virtual {v1}, Landroid/widget/EditText;->selectAll()V

    invoke-virtual {v0}, Landroid/content/Context;->getResources()Landroid/content/res/Resources;

    move-result-object v2

    invoke-virtual {v2}, Landroid/content/res/Resources;->getDisplayMetrics()Landroid/util/DisplayMetrics;

    move-result-object v2

    iget v2, v2, Landroid/util/DisplayMetrics;->density:F

    const/high16 v3, 0x41c00000    # 24.0f

    mul-float v2, v2, v3

    float-to-int v2, v2

    new-instance v3, Landroid/widget/FrameLayout;

    invoke-direct {v3, v0}, Landroid/widget/FrameLayout;-><init>(Landroid/content/Context;)V

    const/4 v4, 0x0

    invoke-virtual {v3, v2, v4, v2, v4}, Landroid/widget/FrameLayout;->setPadding(IIII)V

    invoke-virtual {v3, v1}, Landroid/widget/FrameLayout;->addView(Landroid/view/View;)V

    new-instance v4, Lcom/coui/appcompat/dialog/COUIAlertDialogBuilder;

    invoke-direct {v4, v0}, Lcom/coui/appcompat/dialog/COUIAlertDialogBuilder;-><init>(Landroid/content/Context;)V

    invoke-virtual {p0}, Landroidx/preference/Preference;->getTitle()Ljava/lang/CharSequence;

    move-result-object v2

    invoke-virtual {v4, v2}, Lcom/coui/appcompat/dialog/COUIAlertDialogBuilder;->setTitle(Ljava/lang/CharSequence;)Lcom/coui/appcompat/dialog/COUIAlertDialogBuilder;

    invoke-virtual {v4, v3}, Lcom/coui/appcompat/dialog/COUIAlertDialogBuilder;->setView(Landroid/view/View;)Landroidx/appcompat/app/AlertDialog$Builder;

    new-instance v5, Lcom/android/settings/portmisc/AnimScale$Ok;

    invoke-direct {v5, p0, v1, p1}, Lcom/android/settings/portmisc/AnimScale$Ok;-><init>(Landroidx/preference/Preference;Landroid/widget/EditText;I)V

    const v6, 0x104000a    # android.R.string.ok

    invoke-virtual {v0, v6}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v6

    invoke-virtual {v4, v6, v5}, Lcom/coui/appcompat/dialog/COUIAlertDialogBuilder;->setPositiveButton(Ljava/lang/CharSequence;Landroid/content/DialogInterface$OnClickListener;)Lcom/coui/appcompat/dialog/COUIAlertDialogBuilder;

    const/high16 v6, 0x1040000    # android.R.string.cancel

    invoke-virtual {v0, v6}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v6

    const/4 v5, 0x0

    invoke-virtual {v4, v6, v5}, Lcom/coui/appcompat/dialog/COUIAlertDialogBuilder;->setNegativeButton(Ljava/lang/CharSequence;Landroid/content/DialogInterface$OnClickListener;)Lcom/coui/appcompat/dialog/COUIAlertDialogBuilder;

    invoke-virtual {v4}, Lcom/coui/appcompat/dialog/COUIAlertDialogBuilder;->show()Landroidx/appcompat/app/AlertDialog;

    return-void
.end method

# OK in the number box: apply when 0.5..10, otherwise a toast and nothing changes.
.method static apply(Landroidx/preference/Preference;Landroid/widget/EditText;I)V
    .registers 6

    invoke-virtual {p1}, Landroid/widget/EditText;->getText()Landroid/text/Editable;

    move-result-object v0

    invoke-static {v0}, Lcom/android/settings/portmisc/AnimScale;->parse(Ljava/lang/CharSequence;)F

    move-result v0

    invoke-static {v0}, Lcom/android/settings/portmisc/AnimScale;->ok(F)Z

    move-result v1

    if-nez v1, :cond_ok

    invoke-virtual {p0}, Landroidx/preference/Preference;->getContext()Landroid/content/Context;

    move-result-object v0

    const-string v1, "Enter a speed from 0.5x to 10x"

    const/4 v2, 0x0

    invoke-static {v0, v1, v2}, Landroid/widget/Toast;->makeText(Landroid/content/Context;Ljava/lang/CharSequence;I)Landroid/widget/Toast;

    move-result-object v0

    invoke-virtual {v0}, Landroid/widget/Toast;->show()V

    return-void

    :cond_ok
    invoke-static {p2, v0}, Lcom/android/settings/portmisc/AnimScale;->set(IF)V

    invoke-static {p0}, Lcom/android/settings/portmisc/AnimScale;->refresh(Landroidx/preference/Preference;)V

    return-void
.end method
