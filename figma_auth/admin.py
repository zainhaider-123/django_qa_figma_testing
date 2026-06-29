from django.contrib import admin
from allauth.socialaccount.models import SocialApp
from allauth.socialaccount.admin import SocialAppAdmin as DefaultSocialAppAdmin


admin.site.unregister(SocialApp)


@admin.register(SocialApp)
class SocialAppAdmin(admin.ModelAdmin):
    list_display = ("provider", "client_id_display", "sites_display")
    list_filter = ("provider",)
    search_fields = ("provider", "client_id")
    filter_horizontal = ("sites",)

    @admin.display(description="Client ID")
    def client_id_display(self, obj):
        if obj.client_id:
            return f"{obj.client_id[:6]}…{obj.client_id[-4:]}"
        return "(empty)"

    @admin.display(description="Sites")
    def sites_display(self, obj):
        return ", ".join(str(s) for s in obj.sites.all()) or "(none)"

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        help_texts = {
            "provider": "Use 'figma' — must match the allauth Figma provider.",
            "client_id": "Your Figma OAuth App client ID (from Figma dev settings).",
            "secret": "Your Figma OAuth App client secret (from Figma dev settings).",
            "sites": "Assign the current Site (example.com by default). Required for allauth.",
        }
        for field, text in help_texts.items():
            if field in form.base_fields:
                form.base_fields[field].help_text = text
        return form