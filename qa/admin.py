from django.contrib import admin

from qa.models import TestRun


@admin.register(TestRun)
class TestRunAdmin(admin.ModelAdmin):
    list_display = (
        "frame_name",
        "site_url",
        "status",
        "pass_fail",
        "mismatch_percentage",
        "created_at",
    )
    list_filter = ("status", "pass_fail")
    readonly_fields = ("created_at", "completed_at")
