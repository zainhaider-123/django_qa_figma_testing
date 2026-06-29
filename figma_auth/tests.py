from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken

from .services import FigmaClient, FigmaAPIError

User = get_user_model()


class ConnectionStatusViewTests(TestCase):
    def setUp(self):
        self.url = reverse("figma_auth:status")
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )

    def test_redirects_when_not_logged_in(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_renders_when_logged_in_without_token(self):
        """Logged-in user without a Figma token should see 'not connected'."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Not Connected")
        self.assertContains(response, "Connect Figma")
        self.assertTemplateUsed(response, "figma_auth/status.html")

    @patch("figma_auth.views.SocialToken.objects.get")
    def test_renders_when_logged_in_with_token(self, mock_token_get):
        """Logged-in user with a Figma token should see 'Connected' and user info."""
        mock_token = MagicMock(spec=SocialToken)
        mock_token.token = "fake_token"
        mock_token_get.return_value = mock_token

        self.client.force_login(self.user)

        # Create SocialAccount for the user so extra_data is available
        SocialAccount.objects.create(
            user=self.user,
            provider="figma",
            uid="figma_user_123",
            extra_data={
                "name": "Test Figma User",
                "email": "figma@example.com",
                "handle": "testfigma",
            },
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Connected")
        self.assertContains(response, "Test Figma User")
        self.assertContains(response, "testfigma")
        self.assertContains(response, "figma@example.com")
        self.assertTemplateUsed(response, "figma_auth/status.html")


class ProjectListViewTests(TestCase):
    def setUp(self):
        self.url = reverse("figma_auth:project_list")
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )

    def test_redirects_when_not_logged_in(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    @patch("figma_auth.views.FigmaClient")
    def test_no_token_graceful(self, mock_client_class):
        """If the user has no Figma token, show an error message."""
        mock_client_class.side_effect = FigmaAPIError(
            401, "No Figma token found for this user. Please connect Figma."
        )
        self.client.force_login(self.user)
        # Create SocialAccount with a team_id so we reach FigmaClient init
        SocialAccount.objects.create(
            user=self.user,
            provider="figma",
            uid="figma_uid_1",
            extra_data={"team_id": "123456"},
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Figma token found")

    def test_no_social_account_graceful(self):
        """If the user has no SocialAccount, show an error message."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Figma account connected")

    def test_no_team_id_shows_form(self):
        """If no team_id is stored, show the team ID entry form."""
        self.client.force_login(self.user)
        SocialAccount.objects.create(
            user=self.user,
            provider="figma",
            uid="figma_uid_2",
            extra_data={},
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter your Figma Team ID")
        self.assertContains(response, "name=\"team_id\"")

    @patch("figma_auth.views.FigmaClient")
    def test_with_team_id_fetches_projects(self, mock_client_class):
        """With a stored team_id, fetch and display projects."""
        mock_client = MagicMock()
        mock_client.get_team_projects.return_value = [
            {"id": "proj_1", "name": "My Project"},
        ]
        mock_client_class.return_value = mock_client

        self.client.force_login(self.user)
        SocialAccount.objects.create(
            user=self.user,
            provider="figma",
            uid="figma_uid_3",
            extra_data={"team_id": "team_abc"},
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Project")
        mock_client.get_team_projects.assert_called_once_with("team_abc")


class SaveTeamIdViewTests(TestCase):
    def setUp(self):
        self.url = reverse("figma_auth:save_team_id")
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )

    def test_redirects_when_not_logged_in(self):
        """Anonymous users should be redirected to login."""
        response = self.client.post(self.url, {"team_id": "123"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_get_not_allowed(self):
        """GET should return 405 (require_POST)."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_empty_team_id_shows_error(self):
        """Empty team_id should show an error and redirect."""
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"team_id": ""})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("figma_auth:project_list"))

    def test_saves_team_id_to_extra_data(self):
        """Valid team_id should be stored in SocialAccount.extra_data."""
        self.client.force_login(self.user)
        account = SocialAccount.objects.create(
            user=self.user,
            provider="figma",
            uid="figma_uid_4",
            extra_data={"email": "test@example.com"},
        )
        response = self.client.post(self.url, {"team_id": "999888"})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("figma_auth:project_list"))
        account.refresh_from_db()
        self.assertEqual(account.extra_data["team_id"], "999888")
        # Original extra_data should be preserved
        self.assertEqual(account.extra_data["email"], "test@example.com")


class FileListViewTests(TestCase):
    def setUp(self):
        self.project_id = "12345"
        self.url = reverse("figma_auth:file_list", args=[self.project_id])
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )

    def test_redirects_when_not_logged_in(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    @patch("figma_auth.views.FigmaClient")
    def test_no_token_graceful(self, mock_client_class):
        """If the user has no Figma token, show an error message."""
        mock_client_class.side_effect = FigmaAPIError(
            401, "No Figma token found for this user. Please connect Figma."
        )
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Figma token found")


class FrameTreeViewTests(TestCase):
    def setUp(self):
        self.file_key = "abc123"
        self.url = reverse("figma_auth:frame_tree", args=[self.file_key])
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )

    def test_redirects_when_not_logged_in(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    @patch("figma_auth.views.FigmaClient")
    def test_no_token_graceful(self, mock_client_class):
        """If the user has no Figma token, show an error message."""
        mock_client_class.side_effect = FigmaAPIError(
            401, "No Figma token found for this user. Please connect Figma."
        )
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Figma token found")


class FigmaClientTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="figmauser", password="password123"
        )
        # Create a SocialToken for the user
        SocialAccount.objects.create(
            user=self.user, provider="figma", uid="uid_123"
        )
        self.token = SocialToken.objects.create(
            account=SocialAccount.objects.get(user=self.user, provider="figma"),
            token="test_access_token",
        )

    def test_init_success(self):
        """Creating FigmaClient with a valid user should succeed."""
        client = FigmaClient(self.user)
        self.assertEqual(client.access_token, "test_access_token")

    def test_init_no_token_raises(self):
        """Creating FigmaClient without a token should raise FigmaAPIError."""
        user_no_token = User.objects.create_user(
            username="notoken", password="password123"
        )
        with self.assertRaises(FigmaAPIError) as ctx:
            FigmaClient(user_no_token)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("No Figma token found", str(ctx.exception))

    @patch("requests.Session.request")
    def test_get_me_success(self, mock_request):
        """get_me() should parse and return JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {
            "id": "figma_id",
            "email": "user@example.com",
            "handle": "testhandle",
            "teams": [{"id": "team_1", "name": "My Team"}],
        }
        mock_request.return_value = mock_response

        client = FigmaClient(self.user)
        result = client.get_me()
        self.assertEqual(result["id"], "figma_id")
        self.assertEqual(result["email"], "user@example.com")
        mock_request.assert_called_once()

    @patch("requests.Session.request")
    def test_get_team_projects_success(self, mock_request):
        """get_team_projects() should return the projects list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {
            "projects": [{"id": "proj_1", "name": "Project One"}]
        }
        mock_request.return_value = mock_response

        client = FigmaClient(self.user)
        projects = client.get_team_projects("team_1")
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["name"], "Project One")

    @patch("requests.Session.request")
    def test_get_frame_image_success(self, mock_request):
        """get_frame_image() should download and return PNG bytes."""
        images_response = MagicMock()
        images_response.status_code = 200
        images_response.ok = True
        images_response.json.return_value = {
            "images": {"frame_1": "https://example.com/image.png"}
        }

        png_response = MagicMock()
        png_response.status_code = 200
        png_response.ok = True
        png_response.content = b"fake_png_bytes"

        mock_request.side_effect = [images_response, png_response]

        client = FigmaClient(self.user)
        result = client.get_frame_image("file_key", "frame_1")
        self.assertEqual(result, b"fake_png_bytes")

    @patch("requests.Session.request")
    def test_get_frame_image_missing_node(self, mock_request):
        """get_frame_image() should raise FigmaAPIError when node not in images."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"images": {}}
        mock_request.return_value = mock_response

        client = FigmaClient(self.user)
        with self.assertRaises(FigmaAPIError) as ctx:
            client.get_frame_image("file_key", "nonexistent_node")
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("requests.Session.request")
    def test_401_raises_figma_api_error(self, mock_request):
        """A 401 response should raise FigmaAPIError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.ok = False
        mock_request.return_value = mock_response

        client = FigmaClient(self.user)
        with self.assertRaises(FigmaAPIError) as ctx:
            client.get_me()
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("token is invalid", str(ctx.exception))

    @patch("requests.Session.request")
    def test_429_raises_figma_api_error(self, mock_request):
        """A 429 response should raise FigmaAPIError with rate-limit message."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.ok = False
        mock_request.return_value = mock_response

        client = FigmaClient(self.user)
        with self.assertRaises(FigmaAPIError) as ctx:
            client.get_me()
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("rate limit", str(ctx.exception).lower())

    def test_figma_api_error_repr(self):
        """FigmaAPIError should store status_code and message."""
        exc = FigmaAPIError(418, "I'm a teapot")
        self.assertEqual(exc.status_code, 418)
        self.assertEqual(exc.message, "I'm a teapot")
        self.assertIn("418", str(exc))
        self.assertIn("teapot", str(exc))
