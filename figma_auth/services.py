import requests
from allauth.socialaccount.models import SocialToken


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

    def get_file_tree(self, file_key: str, depth: int = 2) -> dict:
        """
        GET /v1/files/{file_key}?depth={depth}
        Returns the full document tree with pages (CANVAS) and frames (FRAME).
        """
        return self._get(f"/v1/files/{file_key}", params={"depth": depth})

    def get_frame_image(self, file_key: str, node_id: str, scale: int = 2) -> bytes:
        """
        GET /v1/images/{file_key}?ids={node_id}&scale={scale}&format=png
        Returns the PNG image bytes for the given frame node.

        First calls the images endpoint to obtain a signed download URL,
        then downloads the actual PNG binary from that URL.
        """
        data = self._get(
            f"/v1/images/{file_key}",
            params={"ids": node_id, "scale": scale, "format": "png"},
        )
        images = data.get("images", {})
        image_url = images.get(node_id)
        if not image_url:
            raise FigmaAPIError(
                404,
                f"No image URL returned for node '{node_id}'. "
                f"Check that the node_id is a valid frame in file '{file_key}'.",
            )
        # Download the actual PNG bytes from the signed URL (no auth required)
        png_response = requests.get(image_url)
        png_response.raise_for_status()
        return png_response.content
