"""GET /api/v1/redirect/{platform}/{restaurant_id} — affiliate redirect + tracking."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/api/v1", tags=["redirect"])

# Platform base URLs for deep links
PLATFORM_BASE_URLS: dict[str, str] = {
    "wolt": "https://wolt.com/pl/pol/warszawa/restaurant/",
    "pyszne": "https://www.pyszne.pl/menu/",
    "ubereats": "https://www.ubereats.com/pl/store/",
    "glovo": "https://glovoapp.com/pl/pl/warszawa/",
}


@router.get("/redirect/{platform}/{restaurant_id}")
async def redirect_to_platform(platform: str, restaurant_id: str) -> RedirectResponse:
    """Redirect user to the ordering platform.

    Stub — constructs a basic URL. Full affiliate tracking in later sprint.
    """
    base_url = PLATFORM_BASE_URLS.get(platform)
    if base_url is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown platform: {platform}. Supported: {', '.join(PLATFORM_BASE_URLS)}",
        )

    # TODO: look up platform_slug from DB, log affiliate_click, add UTM params
    redirect_url = f"{base_url}{restaurant_id}"

    return RedirectResponse(url=redirect_url, status_code=302)
