import logging
import time

import requests
from allauth.socialaccount.models import SocialToken
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class FigmaAPIError(Exception):
    """Raised when the Figma API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str, *args):
        super().__init__(f"Figma API error {status_code}: {message}", *args)
        self.status_code = status_code
        self.message = message


class FigmaClient:
    """Thin client for the Figma REST API using a user's stored OAuth2 token."""

    BASE_URL = "https://api.figma.com"

    def __init__(self, user):
        try:
            token = SocialToken.objects.get(
                account__user=user, account__provider="figma"
            )
        except SocialToken.DoesNotExist as exc:
            raise FigmaAPIError(
                401, "No Figma token found for this user. Please connect Figma."
            ) from exc
        self.user_id = user.id
        self.access_token = token.token
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {self.access_token}"}
        )

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make an authenticated request to the Figma API and handle errors."""
        url = f"{self.BASE_URL}{path}"
        response = self._session.request(method, url, **kwargs)

        if response.status_code == 401:
            raise FigmaAPIError(
                401,
                "Figma token is invalid or expired. Please reconnect your Figma account.",
            )
        if response.status_code == 403:
            try:
                err = response.json().get("err", "")
            except ValueError:
                err = ""
            if "Request denied" in err:
                raise FigmaAPIError(
                    403,
                    "Figma denied access to this resource. The /teams/ projects "
                    "endpoint requires a PUBLISHED PRIVATE OAuth app. This means "
                    "your app must be (1) set to private, not public, AND (2) "
                    "published — an unpublished private app is still in draft "
                    "state and cannot call REST APIs. Go to figma.com/developers, "
                    "open your app, complete the configuration, click Publish "
                    "(select Private — no Figma review needed), then reconnect "
                    "your Figma account to get a fresh token.",
                )
            raise FigmaAPIError(
                403,
                f"Figma denied access (403): {err or 'Insufficient permissions.'} "
                "Check that your OAuth app has the required scopes and team access.",
            )
        if response.status_code == 429:
            raise FigmaAPIError(
                429,
                "Figma API rate limit exceeded (300 req/min). Please wait and try again.",
            )
        if not response.ok:
            try:
                detail = response.json().get("message") or response.json().get("err") or response.text
            except ValueError:
                detail = response.text
            raise FigmaAPIError(response.status_code, detail)

        return response

    def _get(self, path: str, **kwargs) -> dict:
        """GET request returning parsed JSON."""
        return self._request("GET", path, **kwargs).json()

    def _get_bytes(self, path: str, **kwargs) -> bytes:
        """GET request returning raw bytes."""
        return self._request("GET", path, **kwargs).content

    def get_me(self) -> dict:
        """
        GET /v1/me
        Returns user info including 'email', 'handle', 'id', and 'teams' array.
        """
        return self._get("/v1/me")

    def get_team_projects(self, team_id: str) -> list[dict]:
        """
        GET /v1/teams/{team_id}/projects
        Returns a list of projects belonging to the team.
        """
        data = self._get(f"/v1/teams/{team_id}/projects")
        return data.get("projects", [])

    def get_project_files(self, project_id: str) -> list[dict]:
        """
        GET /v1/projects/{project_id}/files
        Returns a list of files in the project.
        """
        data = self._get(f"/v1/projects/{project_id}/files")
        return data.get("files", [])

    def get_file_tree(self, file_key: str, depth: int = 2, refresh: bool = False) -> dict:
        """
        GET /v1/files/{file_key}?depth={depth}
        Returns the full document tree with pages (CANVAS) and frames (FRAME).

        Responses are cached per user+file+depth to avoid hitting the
        Figma 300 req/min rate limit during development. Pass refresh=True
        to bypass the cache and force a fresh API call (the result is
        still written back to the cache).
        """
        cache_key = f"figma:file_tree:{self.user_id}:{file_key}:d{depth}"
        if not refresh:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit for %s", cache_key)
                return cached

        tree = self._get(f"/v1/files/{file_key}", params={"depth": depth})
        timeout = getattr(settings, "FIGMA_FILE_TREE_CACHE_TIMEOUT", 300)
        cache.set(cache_key, tree, timeout)
        return tree

    def get_frame_image(
        self, file_key: str, node_id: str, scale: float = 2,
        refresh: bool = False,
    ) -> bytes:
        """
        GET /v1/images/{file_key}?ids={node_id}&scale={scale}&format=png
        Returns the PNG image bytes for the given frame node.

        First calls the images endpoint to obtain a signed download URL,
        then downloads the actual PNG binary from that URL.

        If Figma returns a 400 render-timeout error (common for large frames
        at high scale), automatically retries with progressively lower scale
        values (2 → 1 → 0.5) until the render succeeds.

        Responses are cached per user+file+node+scale to avoid hitting the
        Figma 300 req/min rate limit. Pass refresh=True to bypass the cache
        and force a fresh API call (the result is still written back to the
        cache).
        """
        cache_key = f"figma:frame_image:{self.user_id}:{file_key}:{node_id}:s{scale}"
        if not refresh:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit for %s", cache_key)
                return cached

        png_bytes = self._fetch_frame_image(file_key, node_id, scale)
        timeout = getattr(settings, "FIGMA_FRAME_IMAGE_CACHE_TIMEOUT", 600)
        cache.set(cache_key, png_bytes, timeout)
        return png_bytes

    def _fetch_frame_image(
        self, file_key: str, node_id: str, scale: float = 2
    ) -> bytes:
        """Fetch the frame image from the Figma API with scale-fallback retries."""
        scales_to_try = [scale]
        # Build fallback chain down to 0.5
        current = scale
        while current > 0.5:
            current = current / 2
            scales_to_try.append(current)

        last_error = None
        for attempt_scale in scales_to_try:
            try:
                data = self._get(
                    f"/v1/images/{file_key}",
                    params={
                        "ids": node_id,
                        "scale": attempt_scale,
                        "format": "png",
                    },
                )
            except FigmaAPIError as exc:
                if exc.status_code == 400 and "render timeout" in exc.message.lower():
                    logger.warning(
                        "Figma render timeout at scale=%s for node %s, "
                        "retrying at lower scale",
                        attempt_scale,
                        node_id,
                    )
                    last_error = exc
                    time.sleep(1)
                    continue
                raise

            images = data.get("images", {})
            image_url = images.get(node_id)
            if not image_url:
                raise FigmaAPIError(
                    404,
                    f"No image URL returned for node '{node_id}'. "
                    f"Check that the node_id is a valid frame in file "
                    f"'{file_key}'.",
                )
            # Download the actual PNG bytes from the signed URL (no auth required)
            png_response = requests.get(image_url)
            png_response.raise_for_status()
            return png_response.content

        # All scale attempts failed with render timeout
        raise FigmaAPIError(
            400,
            "Figma render timeout at all attempted scales. "
            "The frame may be too large to render. Try selecting a "
            "smaller frame or component.",
        ) from last_error
