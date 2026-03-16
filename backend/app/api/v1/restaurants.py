"""GET /api/v1/restaurants/{id}/menu — unified menu with per-platform prices."""

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.dependencies import DbSession
from app.models.menu import CanonicalMenuItem, MenuCategory, PlatformMenuItem
from app.models.modifier import ModifierGroup, ModifierOption
from app.models.restaurant import CanonicalRestaurant, PlatformRestaurant
from app.schemas.menu import (
    MenuCategorySchema,
    MenuItem,
    MenuResponse,
    ModifierGroupSchema,
    ModifierOptionSchema,
    PlatformPrice,
)

router = APIRouter(prefix="/api/v1", tags=["restaurants"])


@router.get("/restaurants/{restaurant_id}/menu", response_model=MenuResponse)
async def get_restaurant_menu(restaurant_id: str, db: DbSession) -> MenuResponse:
    """Return unified menu for a canonical restaurant with per-platform prices and modifiers."""

    # ── Validate UUID ───────────────────────────────────────
    try:
        rid = _uuid.UUID(restaurant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid restaurant ID format")

    # ── Load restaurant with full menu tree ─────────────────
    stmt = (
        select(CanonicalRestaurant)
        .where(CanonicalRestaurant.id == rid, CanonicalRestaurant.is_active.is_(True))
        .options(
            selectinload(CanonicalRestaurant.menu_categories)
            .selectinload(MenuCategory.canonical_menu_items)
            .selectinload(CanonicalMenuItem.platform_menu_items)
            .selectinload(PlatformMenuItem.modifier_groups)
            .selectinload(ModifierGroup.modifier_options),
            selectinload(CanonicalRestaurant.menu_categories)
            .selectinload(MenuCategory.canonical_menu_items)
            .selectinload(CanonicalMenuItem.platform_menu_items)
            .selectinload(PlatformMenuItem.platform_restaurant),
        )
    )

    result = await db.execute(stmt)
    restaurant = result.scalar_one_or_none()

    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    # ── Collect available platforms ─────────────────────────
    platforms_set: set[str] = set()

    # ── Build category → items → platform prices ────────────
    categories: list[MenuCategorySchema] = []

    for cat in sorted(restaurant.menu_categories, key=lambda c: c.sort_order):
        items: list[MenuItem] = []

        for cmi in cat.canonical_menu_items:
            platform_prices: list[PlatformPrice] = []

            for pmi in cmi.platform_menu_items:
                if not pmi.is_available:
                    continue

                platform_name = pmi.platform_restaurant.platform if pmi.platform_restaurant else "unknown"
                platforms_set.add(platform_name)

                # Build modifier groups
                mod_groups: list[ModifierGroupSchema] = []
                for mg in sorted(pmi.modifier_groups, key=lambda g: g.sort_order):
                    options = [
                        ModifierOptionSchema(
                            id=str(mo.id),
                            name=mo.name,
                            price_grosz=mo.price_grosz,
                            is_default=mo.is_default,
                            is_available=mo.is_available,
                            platform_option_id=mo.platform_option_id,
                        )
                        for mo in mg.modifier_options
                        if mo.is_available
                    ]
                    mod_groups.append(
                        ModifierGroupSchema(
                            id=str(mg.id),
                            name=mg.name,
                            group_type=mg.group_type,
                            min_selections=mg.min_selections,
                            max_selections=mg.max_selections,
                            options=options,
                        )
                    )

                platform_prices.append(
                    PlatformPrice(
                        platform=platform_name,
                        platform_item_id=pmi.platform_item_id,
                        platform_name=pmi.platform_name,
                        price_grosz=pmi.price_grosz,
                        is_available=pmi.is_available,
                        last_scraped_at=(
                            pmi.last_scraped_at.isoformat() if pmi.last_scraped_at else None
                        ),
                        modifier_groups=mod_groups,
                    )
                )

            items.append(
                MenuItem(
                    id=str(cmi.id),
                    name=cmi.name,
                    description=cmi.description,
                    size_label=cmi.size_label,
                    platform_prices=platform_prices,
                )
            )

        categories.append(
            MenuCategorySchema(
                id=str(cat.id),
                name=cat.name,
                sort_order=cat.sort_order,
                items=items,
            )
        )

    return MenuResponse(
        restaurant_id=str(restaurant.id),
        restaurant_name=restaurant.name,
        categories=categories,
        platforms_available=sorted(platforms_set),
    )
