from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

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
    """List projects from the user's Figma team.

    The Figma API does not return team IDs from /v1/me, so the user must
    provide their team ID once. It is stored in SocialAccount.extra_data
    and reused on subsequent visits.
    """
    try:
        account = SocialAccount.objects.get(
            user=request.user, provider="figma"
        )
    except SocialAccount.DoesNotExist:
        messages.error(request, "No Figma account connected. Please connect Figma first.")
        return render(request, "figma_auth/project_list.html", {"projects": []})

    team_id = account.extra_data.get("team_id")

    # No team ID stored yet — ask the user to provide it
    if not team_id:
        return render(
            request,
            "figma_auth/project_list.html",
            {"projects": [], "need_team_id": True},
        )

    # Fetch projects for the stored team ID
    try:
        client = FigmaClient(request.user)
    except FigmaAPIError as exc:
        messages.error(request, str(exc))
        return render(
            request,
            "figma_auth/project_list.html",
            {"projects": [], "team_id": team_id},
        )

    try:
        team_projects = client.get_team_projects(team_id)
    except FigmaAPIError as exc:
        messages.error(request, f"Could not fetch projects: {exc.message}")
        return render(
            request,
            "figma_auth/project_list.html",
            {"projects": [], "team_id": team_id},
        )

    context = {
        "projects": team_projects,
        "team_id": team_id,
    }
    return render(request, "figma_auth/project_list.html", context)


@login_required
@require_POST
def save_team_id(request):
    """Save the user's Figma team ID to SocialAccount.extra_data."""
    team_id = request.POST.get("team_id", "").strip()
    if not team_id:
        messages.error(request, "Please provide a team ID.")
        return redirect("figma_auth:project_list")

    try:
        account = SocialAccount.objects.get(
            user=request.user, provider="figma"
        )
    except SocialAccount.DoesNotExist:
        messages.error(request, "No Figma account connected. Please connect Figma first.")
        return redirect("figma_auth:project_list")

    extra = account.extra_data or {}
    extra["team_id"] = team_id
    account.extra_data = extra
    account.save()
    messages.success(request, "Team ID saved. Loading projects...")
    return redirect("figma_auth:project_list")


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

    refresh = request.GET.get("refresh") == "1"

    try:
        tree = client.get_file_tree(file_key, depth=2, refresh=refresh)
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
