from django.contrib.auth.models import User
from django.db import models


class TestRun(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file_key = models.CharField(max_length=255)
    node_id = models.CharField(max_length=255)
    frame_name = models.CharField(max_length=255)
    frame_width = models.IntegerField()
    frame_height = models.IntegerField()
    site_url = models.URLField()
    status = models.CharField(max_length=20, default='pending')  # pending/running/completed/failed
    figma_image = models.ImageField(upload_to='figma/', null=True, blank=True)
    site_screenshot = models.ImageField(upload_to='screenshots/', null=True, blank=True)
    diff_image = models.ImageField(upload_to='diffs/', null=True, blank=True)
    mismatch_percentage = models.FloatField(null=True, blank=True)
    mismatch_pixels = models.IntegerField(null=True, blank=True)
    threshold = models.FloatField(default=0.10)
    pass_fail = models.CharField(max_length=10, null=True, blank=True)  # pass/fail
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.frame_name} vs {self.site_url} ({self.status})"
