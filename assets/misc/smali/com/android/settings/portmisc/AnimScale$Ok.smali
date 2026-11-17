.class final Lcom/android/settings/portmisc/AnimScale$Ok;
.super Ljava/lang/Object;
.source "AnimScale.java"

# interfaces
.implements Landroid/content/DialogInterface$OnClickListener;


.field final pref:Landroidx/preference/Preference;

.field final edit:Landroid/widget/EditText;

.field final which:I


.method constructor <init>(Landroidx/preference/Preference;Landroid/widget/EditText;I)V
    .registers 4

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    iput-object p1, p0, Lcom/android/settings/portmisc/AnimScale$Ok;->pref:Landroidx/preference/Preference;

    iput-object p2, p0, Lcom/android/settings/portmisc/AnimScale$Ok;->edit:Landroid/widget/EditText;

    iput p3, p0, Lcom/android/settings/portmisc/AnimScale$Ok;->which:I

    return-void
.end method

.method public onClick(Landroid/content/DialogInterface;I)V
    .registers 6

    iget-object v0, p0, Lcom/android/settings/portmisc/AnimScale$Ok;->pref:Landroidx/preference/Preference;

    iget-object v1, p0, Lcom/android/settings/portmisc/AnimScale$Ok;->edit:Landroid/widget/EditText;

    iget v2, p0, Lcom/android/settings/portmisc/AnimScale$Ok;->which:I

    invoke-static {v0, v1, v2}, Lcom/android/settings/portmisc/AnimScale;->apply(Landroidx/preference/Preference;Landroid/widget/EditText;I)V

    return-void
.end method
