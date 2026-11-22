.class public Lcom/android/settings/portmisc/PortSearchPref;
.super Lcom/android/settingslib/widget/LayoutPreference;
.source "PortSearchPref.java"

# Row that holds the Choose apps search bar. LayoutPreference.onBindViewHolder runs removeAllViews() and re-adds its
# view on every bind; the list rebinds on each typed letter (rows shown/hidden), and moving the focused search field
# closed the keyboard. Skip the re-add while the bar is already in this row (see AppsFragment.onViewCreated too).


# instance fields
.field private v:Landroid/view/View;


.method public constructor <init>(Landroid/content/Context;Landroid/view/View;)V
    .registers 3

    invoke-direct {p0, p1, p2}, Lcom/android/settingslib/widget/LayoutPreference;-><init>(Landroid/content/Context;Landroid/view/View;)V

    iput-object p2, p0, Lcom/android/settings/portmisc/PortSearchPref;->v:Landroid/view/View;

    return-void
.end method

.method public onBindViewHolder(Landroidx/preference/PreferenceViewHolder;)V
    .registers 4

    iget-object v0, p0, Lcom/android/settings/portmisc/PortSearchPref;->v:Landroid/view/View;

    invoke-virtual {v0}, Landroid/view/View;->getParent()Landroid/view/ViewParent;

    move-result-object v0

    iget-object v1, p1, Landroidx/recyclerview/widget/RecyclerView$ViewHolder;->itemView:Landroid/view/View;

    if-ne v0, v1, :cond_bind

    return-void

    :cond_bind
    invoke-super {p0, p1}, Lcom/android/settingslib/widget/LayoutPreference;->onBindViewHolder(Landroidx/preference/PreferenceViewHolder;)V

    return-void
.end method
