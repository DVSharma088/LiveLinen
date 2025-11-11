from django import forms
from .models import PackagingStage

class StageCompleteForm(forms.ModelForm):
    class Meta:
        model = PackagingStage
        fields = ['image']

class ConfirmReceivedForm(forms.Form):
    confirm = forms.BooleanField(required=True)
