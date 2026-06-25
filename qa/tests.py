from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class DashboardViewTests(TestCase):
    def test_dashboard_redirects_when_not_logged_in(self):
        """Unauthenticated users should be redirected to login."""
        response = self.client.get(reverse("qa:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_dashboard_renders_when_logged_in(self):
        """Authenticated users should see the dashboard."""
        User.objects.create_user(username="testuser", password="secret")
        self.client.login(username="testuser", password="secret")
        response = self.client.get(reverse("qa:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")
        self.assertContains(response, "New Test Run")


class NewRunViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="secret")

    def test_new_run_redirects_when_not_logged_in(self):
        response = self.client.get(reverse("qa:new_run"))
        self.assertEqual(response.status_code, 302)

    def test_new_run_get_renders_form(self):
        self.client.login(username="testuser", password="secret")
        url = reverse("qa:new_run") + "?file_key=abc&node_id=1:2&frame_name=Test&frame_width=800&frame_height=600"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Test Run")
        self.assertContains(response, "site_url")
        self.assertContains(response, "threshold")

    def test_new_run_redirects_without_frame_params(self):
        """Without frame selection query params, should redirect to project list."""
        self.client.login(username="testuser", password="secret")
        response = self.client.get(reverse("qa:new_run"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/figma/", response.url)


class RunListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="secret")

    def test_run_list_redirects_when_not_logged_in(self):
        response = self.client.get(reverse("qa:run_list"))
        self.assertEqual(response.status_code, 302)

    def test_run_list_renders_when_logged_in(self):
        self.client.login(username="testuser", password="secret")
        response = self.client.get(reverse("qa:run_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Run History")


class RunReportViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="secret")

    def test_run_report_requires_login(self):
        response = self.client.get(reverse("qa:run_report", args=[1]))
        self.assertEqual(response.status_code, 302)

    def test_run_report_404_for_other_users_run(self):
        """A user should not see another user's test run."""
        self.client.login(username="testuser", password="secret")
        response = self.client.get(reverse("qa:run_report", args=[999]))
        self.assertEqual(response.status_code, 404)
