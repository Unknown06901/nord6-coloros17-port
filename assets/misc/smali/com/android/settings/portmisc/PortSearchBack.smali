.class public Lcom/android/settings/portmisc/PortSearchBack;
.super Landroidx/activity/OnBackPressedCallback;
.source "PortSearchBack.java"

# Back on the Choose apps page while the search is open closes the search (clears the text) instead of the page.
# Enabled only while the search is open; registered with the activity's OnBackPressedDispatcher, which is what
# Back goes through on Android 17 (Activity.onBackPressed overrides such as OplusSubSettings' callback aren't called).


# instance fields
.field private final f:Lcom/android/settings/portmisc/AppsFragment;


.method public constructor <init>(Lcom/android/settings/portmisc/AppsFragment;)V
    .registers 3

    const/4 v0, 0x0

    invoke-direct {p0, v0}, Landroidx/activity/OnBackPressedCallback;-><init>(Z)V

    iput-object p1, p0, Lcom/android/settings/portmisc/PortSearchBack;->f:Lcom/android/settings/portmisc/AppsFragment;

    return-void
.end method

.method public handleOnBackPressed()V
    .registers 2

    iget-object v0, p0, Lcom/android/settings/portmisc/PortSearchBack;->f:Lcom/android/settings/portmisc/AppsFragment;

    invoke-virtual {v0}, Lcom/android/settings/portmisc/AppsFragment;->closeSearch()Z

    return-void
.end method
