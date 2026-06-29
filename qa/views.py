import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from figma_auth.services import FigmaClient, FigmaAPIError

from qa.models import TestRun
from qa.services import CompareService, ScreenshotService

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    """Landing page showing recent test runs and a prompt to start a new test."""
    recent_runs = TestRun.objects.filter(user=request.user)[:5]
    return render(request, "qa/dashboard.html", {"recent_runs": recent_runs})


@login_required
def new_run(request):
    """Create and execute a new test run synchronously.

    GET:  Displays a form pre-populated with frame info from query params.
    POST: Creates a TestRun, runs the full comparison pipeline, and redirects
          to the report page.
    """
    if request.method == "POST":
        file_key = request.POST.get("file_key", "").strip()
        node_id = request.POST.get("node_id", "").strip()
        frame_name = request.POST.get("frame_name", "").strip()
        site_url = request.POST.get("site_url", "").strip()

        if not all([file_key, node_id, frame_name, site_url]):
            messages.error(request, "Missing required fields. Please select a frame first.")
            return redirect("figma_auth:project_list")

        try:
            frame_width = int(request.POST["frame_width"])
            frame_height = int(request.POST["frame_height"])
        except (KeyError, ValueError):
            messages.error(request, "Invalid frame dimensions.")
            return redirect("figma_auth:project_list")

        threshold = float(request.POST.get("threshold", 0.10))

        run = TestRun.objects.create(
            user=request.user,
            file_key=file_key,
            node_id=node_id,
            frame_name=frame_name,
            frame_width=frame_width,
            frame_height=frame_height,
            site_url=site_url,
            threshold=threshold,
            status="running",
        )

        refresh = request.GET.get("refresh") == "1"

        try:
            # 1. Fetch Figma frame image
            client = FigmaClient(request.user)
            figma_png = client.get_frame_image(
                file_key, node_id, scale=2, refresh=refresh
            )
            run.figma_image.save(
                f"{run.id}_figma.png", ContentFile(figma_png), save=False
            )

            # 2. Capture site screenshot
            screenshot_png = ScreenshotService.capture(
                site_url, frame_width, frame_height
            )
            run.site_screenshot.save(
                f"{run.id}_screenshot.png", ContentFile(screenshot_png), save=False
            )

            # 3. Compare images
            result = CompareService.compare(
                figma_png, screenshot_png, threshold=threshold
            )
            run.diff_image.save(
                f"{run.id}_diff.png",
                ContentFile(result["diff_image_bytes"]),
                save=False,
            )
            run.mismatch_pixels = result["mismatch_pixels"]
            run.mismatch_percentage = result["mismatch_percentage"]
            run.pass_fail = "pass" if result["pass"] else "fail"

            run.status = "completed"
            run.completed_at = timezone.now()
            run.save()

            messages.success(request, "Test run completed successfully.")
            return redirect("qa:run_report", run_id=run.id)

        except (FigmaAPIError, RuntimeError, Exception) as exc:
            logger.exception("Test run %s failed", run.id)
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = timezone.now()
            run.save()

            messages.error(request, f"Test run failed: {exc}")
            return redirect("qa:run_report", run_id=run.id)

    # GET — show form (pre-populated from query params)
    file_key = request.GET.get("file_key", "").strip()
    if not file_key:
        messages.info(request, "Select a Figma frame to start a new test.")
        return redirect("figma_auth:project_list")

    context = {
        "file_key": file_key,
        "node_id": request.GET.get("node_id", ""),
        "frame_name": request.GET.get("frame_name", ""),
        "frame_width": request.GET.get("frame_width", ""),
        "frame_height": request.GET.get("frame_height", ""),
        "threshold": request.GET.get("threshold", "0.10"),
    }
    return render(request, "qa/new_run.html", context)


@login_required
def run_report(request, run_id):
    """Display the test run report with images and metrics."""
    run = get_object_or_404(TestRun, id=run_id, user=request.user)
    return render(request, "qa/run_report.html", {"run": run})


@login_required
def run_list(request):
    """History of all test runs for the current user."""
    runs = TestRun.objects.filter(user=request.user)
    return render(request, "qa/run_list.html", {"runs": runs})


@login_required
@require_POST
def rerun(request, run_id):
    """Re-run a previous test with the same parameters."""
    original = get_object_or_404(TestRun, id=run_id, user=request.user)

    new_run = TestRun.objects.create(
        user=request.user,
        file_key=original.file_key,
        node_id=original.node_id,
        frame_name=original.frame_name,
        frame_width=original.frame_width,
        frame_height=original.frame_height,
        site_url=original.site_url,
        threshold=original.threshold,
        status="running",
    )

    refresh = request.GET.get("refresh") == "1"

    try:
        client = FigmaClient(request.user)
        figma_png = client.get_frame_image(
            new_run.file_key, new_run.node_id, scale=2, refresh=refresh
        )
        new_run.figma_image.save(
            f"{new_run.id}_figma.png", ContentFile(figma_png), save=False
        )

        screenshot_png = ScreenshotService.capture(
            new_run.site_url, new_run.frame_width, new_run.frame_height
        )
        new_run.site_screenshot.save(
            f"{new_run.id}_screenshot.png", ContentFile(screenshot_png), save=False
        )

        result = CompareService.compare(
            figma_png, screenshot_png, threshold=new_run.threshold
        )
        new_run.diff_image.save(
            f"{new_run.id}_diff.png",
            ContentFile(result["diff_image_bytes"]),
            save=False,
        )
        new_run.mismatch_pixels = result["mismatch_pixels"]
        new_run.mismatch_percentage = result["mismatch_percentage"]
        new_run.pass_fail = "pass" if result["pass"] else "fail"

        new_run.status = "completed"
        new_run.completed_at = timezone.now()
        new_run.save()

        messages.success(request, "Re-run completed successfully.")
    except (FigmaAPIError, RuntimeError, Exception) as exc:
        logger.exception("Re-run %s failed", new_run.id)
        new_run.status = "failed"
        new_run.error_message = str(exc)
        new_run.completed_at = timezone.now()
        new_run.save()

        messages.error(request, f"Re-run failed: {exc}")

    return redirect("qa:run_report", run_id=new_run.id)
