from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone

from bookmarks.models import Bookmark, BookmarkVote
from bookmarks.type_defs import HttpRequest
from bookmarks.utils import get_safe_return_url

PERIODS = {
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
    "year": timedelta(days=365),
}

PERIOD_LABELS = [
    ("day", "Day"),
    ("week", "Week"),
    ("month", "Month"),
    ("year", "Year"),
]


def _get_hn_queryset(user, tag_name, period):
    cutoff = timezone.now() - PERIODS[period]
    user_vote_qs = BookmarkVote.objects.filter(
        bookmark=OuterRef("pk"), user=user
    )

    return (
        Bookmark.objects.filter(
            tags__name__iexact=tag_name,
            date_added__gte=cutoff,
        )
        .annotate(
            vote_count=Count("votes", distinct=True),
            has_voted=Exists(user_vote_qs),
        )
        .select_related("owner")
        .prefetch_related("tags")
        .order_by("-vote_count", "-date_added")
    )


@login_required
def index(request: HttpRequest):
    tag_name = request.user_profile.hn_tag_name

    if not tag_name:
        return render(
            request,
            "bookmarks/hn.html",
            {
                "page_title": "Hacker News - Linkding",
                "no_tag_configured": True,
                "period_labels": PERIOD_LABELS,
                "current_period": "day",
            },
        )

    explicit_period = request.GET.get("period")
    period = explicit_period or "day"
    if period not in PERIODS:
        period = "day"

    queryset = _get_hn_queryset(request.user, tag_name, period)

    # Fallback: if no explicit period was set and day is empty, try week
    fell_back = False
    if not explicit_period and period == "day" and not queryset.exists():
        period = "week"
        queryset = _get_hn_queryset(request.user, tag_name, period)
        fell_back = True

    page_number = request.GET.get("page")
    paginator = Paginator(queryset, request.user_profile.items_per_page)
    page = paginator.get_page(page_number)

    return render(
        request,
        "bookmarks/hn.html",
        {
            "page_title": "Hacker News - Linkding",
            "items": page,
            "is_empty": paginator.count == 0,
            "total": paginator.count,
            "period_labels": PERIOD_LABELS,
            "current_period": period,
            "fell_back": fell_back,
            "tag_name": tag_name,
            "no_tag_configured": False,
        },
    )


@login_required
def vote(request: HttpRequest, bookmark_id: int):
    if request.method != "POST":
        return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/"))

    try:
        bookmark = Bookmark.objects.get(pk=bookmark_id)
    except Bookmark.DoesNotExist:
        return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/"))

    BookmarkVote.objects.get_or_create(user=request.user, bookmark=bookmark)

    return_url = get_safe_return_url(
        request.POST.get("return_url"), "/bookmarks/hn"
    )
    return HttpResponseRedirect(return_url)
