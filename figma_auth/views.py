from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages

from allauth.socialaccount.models import SocialAccount, SocialToken

from .services import FigmaClient, FigmaAPIError


@login_required
def connection_status(request):
    """Show the user's Figma connection status and account info if connected."""
    connected = False
    figma_user = None

    try:
        token = SocialToken.objects.get(
            account__user=request.user, account__provider="figma"
        )
        connected = bool(token.token)
    except SocialToken.DoesNotExist:
        pass

    if connected:
        try:
            account = SocialAccount.objects.get(
                user=request.user, provider="figma"
            )
            figma_user = {
                "uid": account.uid,
                "name": account.extra_data.get("name", ""),
                "email": account.extra_data.get("email", ""),
                "handle": account.extra_data.get("handle", ""),
            }
        except SocialAccount.DoesNotExist:
            pass

    context = {
        "connected": connected,
        "figma_user": figma_user,
    }
    return render(request, "figma_auth/status.html", context)


@login_required
def project_list(request):
    """List projects from the user's Figma teams."""
    try:
        client = FigmaClient(request.user)
    except FigmaAPIError as exc:
        messages.error(request, str(exc))
        return render(request, "figma_auth/project_list.html", {"projects": []})

    try:
        me = client.get_me()
    except FigmaAPIError as exc:
        messages.error(request, f"Could not fetch Figma user info: {exc.message}")
        return render(request, "figma_auth/project_list.html", {"projects": []})

    teams = me.get("teams", [])
    projects = []

    for team in teams:
        team_id = team.get("id")
        team_name = team.get("name", "Unknown Team")
        try:
            team_projects = client.get_team_projects(team_id)
            for proj in team_projects:
                proj["team_name"] = team_name
            projects.extend(team_projects)
        except FigmaAPIError as exc:
            messages.warning(
                request,
                f"Could not load projects for team '{team_name}': {exc.message}",
            )

    context = {
        "projects": projects,
    }
    return render(request, "figma_auth/project_list.html", context)


@login_required
def file_list(request, project_id):
    """List files in a Figma project."""
    try:
        client = FigmaClient(request.user)
    except FigmaAPIError as exc:
        messages.error(request, str(exc))
        return render(request, "figma_auth/file_list.html", {"files": []})

    try:
        files = client.get_project_files(project_id)
    except FigmaAPIError as exc:
        messages.error(request, f"Could not fetch files: {exc.message}")
        files = []

    context = {
        "files": files,
        "project_id": project_id,
    }
    return render(request, "figma_auth/file_list.html", context)


@login_required
def frame_tree(request, file_key):
    """
    Fetch the Figma file tree and display pages (CANVAS) → frames (FRAME).
    Each frame is selectable and links to qa:new_run with query params.
    """
    try:
        client = FigmaClient(request.user)
    except FigmaAPIError as exc:
        messages.error(request, str(exc))
        return render(request, "figma_auth/frame_tree.html", {"pages": []})

    try:
        tree = client.get_file_tree(file_key, depth=2)
    except FigmaAPIError as exc:
        messages.error(request, f"Could not fetch file tree: {exc.message}")
        return render(request, "figma_auth/frame_tree.html", {"pages": []})

    document = tree.get("document", {})
    raw_pages = document.get("children", [])

    pages = []
    for page in raw_pages:
        if page.get("type") != "CANVAS":
            continue
        frames = []
        for child in page.get("children", []):
            if child.get("type") != "FRAME":
                continue
            bbox = child.get("absoluteBoundingBox", {})
            frames.append(
                {
                    "node_id": child.get("id", ""),
                    "name": child.get("name", "Unnamed Frame"),
                    "width": bbox.get("width", 0),
                    "height": bbox.get("height", 0),
                }
            )
        pages.append(
            {
                "name": page.get("name", "Unnamed Page"),
                "frames": frames,
            }
        )

    context = {
        "pages": pages,
        "file_key": file_key,
    }
    return render(request, "figma_auth/frame_tree.html", context)
