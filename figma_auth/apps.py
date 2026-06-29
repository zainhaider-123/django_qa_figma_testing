from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.conf import settings


class FigmaAuthConfig(AppConfig):
    name = 'figma_auth'

    def ready(self):
        post_migrate.connect(self._seed_figma_socialapp, sender=self)
        # Patch allauth's Figma adapter to fix two issues:
        #   1. Figma requires HTTP Basic Auth for token exchange, but the
        #      allauth adapter defaults to sending credentials in the POST body.
        #   2. The token URL in allauth (www.figma.com/api/oauth/token) is
        #      outdated; the current endpoint is api.figma.com/v1/oauth/token.
        from allauth.socialaccount.providers.figma.views import FigmaOAuth2Adapter

        FigmaOAuth2Adapter.access_token_url = "https://api.figma.com/v1/oauth/token"
        FigmaOAuth2Adapter.basic_auth = True

    def _seed_figma_socialapp(self, *, sender, **kwargs):
        """Ensure a placeholder Figma SocialApp row exists, assigned to Site 1."""
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site

        site_id = getattr(settings, "SITE_ID", 1)
        site = Site.objects.filter(pk=site_id).first()
        if not site:
            return

        app, created = SocialApp.objects.get_or_create(
            provider="figma",
            defaults={"client_id": "", "secret": ""},
        )
        if not app.sites.filter(pk=site_id).exists():
            app.sites.add(site)