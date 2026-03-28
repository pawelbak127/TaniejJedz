"""Seed script: inserts 12 Warsaw restaurants with menus, platforms, modifiers, delivery fees.

Usage:
    docker compose -f docker-compose.dev.yml run --rm api python seed.py
"""

import asyncio
import uuid
from datetime import datetime, time, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.base import Base
from app.models.city import City
from app.models.restaurant import CanonicalRestaurant, PlatformRestaurant, OperatingHours
from app.models.menu import MenuCategory, CanonicalMenuItem, PlatformMenuItem
from app.models.modifier import ModifierGroup, ModifierOption
from app.models.delivery import DeliveryFee
from app.models.feature_flag import FeatureFlag

settings = get_settings()
now = datetime.now(timezone.utc)


def uid() -> uuid.UUID:
    return uuid.uuid4()


RESTAURANTS = [
    {
        "name": "Pizzeria Roma",
        "normalized_name": "roma",
        "address_street": "Marszałkowska 10",
        "address_city": "Warszawa",
        "lat": 52.2298, "lng": 21.0118,
        "cuisine_tags": ["pizza", "włoska"],
        "image_url": "https://images.taniejjedz.pl/seed/roma.jpg",
        "quality": 0.92,
        "platforms": [
            {"platform": "wolt", "pid": "roma-wolt-001", "slug": "pizzeria-roma", "fee": 599, "minutes": 35},
            {"platform": "pyszne", "pid": "roma-pyszne-001", "slug": "pizzeria-roma-warszawa", "fee": 499, "minutes": 40},
        ],
        "categories": [
            {
                "name": "Pizza",
                "items": [
                    {"name": "Margherita 32cm", "desc": "Sos pomidorowy, mozzarella, bazylia", "size": "32cm",
                     "prices": {"wolt": 2650, "pyszne": 2800},
                     "modifiers": [
                         {"name": "Rozmiar", "type": "required", "min": 1, "max": 1,
                          "options": [("32cm", 0), ("40cm", 800), ("50cm", 1500)]},
                         {"name": "Dodatki", "type": "optional", "min": 0, "max": 5,
                          "options": [("Dodatkowy ser", 350), ("Szynka", 400), ("Pieczarki", 300), ("Oliwki", 350)]},
                     ]},
                    {"name": "Pepperoni 32cm", "desc": "Sos pomidorowy, mozzarella, pepperoni", "size": "32cm",
                     "prices": {"wolt": 3100, "pyszne": 3200}, "modifiers": []},
                    {"name": "Capricciosa 32cm", "desc": "Sos, mozzarella, szynka, pieczarki", "size": "32cm",
                     "prices": {"wolt": 3200, "pyszne": 3400}, "modifiers": []},
                ],
            },
            {
                "name": "Desery",
                "items": [
                    {"name": "Tiramisu", "desc": "Klasyczne tiramisu", "size": None,
                     "prices": {"wolt": 1800, "pyszne": 1900}, "modifiers": []},
                ],
            },
        ],
    },
    {
        "name": "Sushi Master",
        "normalized_name": "sushi master",
        "address_street": "Nowy Świat 22",
        "address_city": "Warszawa",
        "lat": 52.2316, "lng": 21.0186,
        "cuisine_tags": ["sushi", "japońska"],
        "image_url": "https://images.taniejjedz.pl/seed/sushi-master.jpg",
        "quality": 0.88,
        "platforms": [
            {"platform": "wolt", "pid": "sushi-wolt-001", "slug": "sushi-master", "fee": 799, "minutes": 45},
            {"platform": "pyszne", "pid": "sushi-pyszne-001", "slug": "sushi-master-warszawa", "fee": 699, "minutes": 50},
        ],
        "categories": [
            {
                "name": "Zestawy",
                "items": [
                    {"name": "Zestaw Sake 16szt", "desc": "Mix nigiri i maki z łososiem", "size": "16szt",
                     "prices": {"wolt": 5900, "pyszne": 6200}, "modifiers": []},
                    {"name": "Zestaw Mix 24szt", "desc": "Nigiri, maki, uramaki", "size": "24szt",
                     "prices": {"wolt": 7900, "pyszne": 8200}, "modifiers": []},
                ],
            },
            {
                "name": "Nigiri",
                "items": [
                    {"name": "Nigiri Łosoś 2szt", "desc": "Świeży łosoś na ryżu", "size": "2szt",
                     "prices": {"wolt": 1200, "pyszne": 1400},
                     "modifiers": [
                         {"name": "Sos", "type": "optional", "min": 0, "max": 2,
                          "options": [("Sos sojowy", 0), ("Wasabi extra", 200), ("Imbir extra", 150)]},
                     ]},
                ],
            },
        ],
    },
    {
        "name": "Burger Joint",
        "normalized_name": "burger joint",
        "address_street": "Chmielna 5",
        "address_city": "Warszawa",
        "lat": 52.2321, "lng": 21.0098,
        "cuisine_tags": ["burgery", "amerykańska"],
        "image_url": "https://images.taniejjedz.pl/seed/burger-joint.jpg",
        "quality": 0.90,
        "platforms": [
            {"platform": "wolt", "pid": "burger-wolt-001", "slug": "burger-joint", "fee": 499, "minutes": 30},
            {"platform": "pyszne", "pid": "burger-pyszne-001", "slug": "burger-joint-warszawa", "fee": 599, "minutes": 35},
        ],
        "categories": [
            {
                "name": "Burgery",
                "items": [
                    {"name": "Classic Burger", "desc": "Wołowina 200g, sałata, pomidor, cebula", "size": None,
                     "prices": {"wolt": 2800, "pyszne": 2900},
                     "modifiers": [
                         {"name": "Mięso", "type": "required", "min": 1, "max": 1,
                          "options": [("Wołowina", 0), ("Kurczak", 0), ("Beyond Meat", 500)]},
                         {"name": "Dodatki", "type": "optional", "min": 0, "max": 4,
                          "options": [("Bekon", 400), ("Jalapeno", 200), ("Cheddar", 300), ("Jajko", 300)]},
                     ]},
                    {"name": "Double Smash", "desc": "2x wołowina 100g, cheddar, pickles", "size": None,
                     "prices": {"wolt": 3400, "pyszne": 3600}, "modifiers": []},
                ],
            },
            {
                "name": "Frytki",
                "items": [
                    {"name": "Frytki klasyczne", "desc": "Chrupiące frytki", "size": None,
                     "prices": {"wolt": 900, "pyszne": 1000}, "modifiers": []},
                ],
            },
        ],
    },
    {
        "name": "Kebab Sultan",
        "normalized_name": "sultan",
        "address_street": "Złota 44",
        "address_city": "Warszawa",
        "lat": 52.2288, "lng": 21.0045,
        "cuisine_tags": ["kebab", "turecka"],
        "image_url": "https://images.taniejjedz.pl/seed/sultan.jpg",
        "quality": 0.85,
        "platforms": [
            {"platform": "wolt", "pid": "sultan-wolt-001", "slug": "kebab-sultan", "fee": 399, "minutes": 25},
            {"platform": "pyszne", "pid": "sultan-pyszne-001", "slug": "kebab-sultan-warszawa", "fee": 299, "minutes": 30},
        ],
        "categories": [
            {
                "name": "Kebaby",
                "items": [
                    {"name": "Kebab duży", "desc": "Mięso, surówki, sos", "size": "duży",
                     "prices": {"wolt": 2200, "pyszne": 2000}, "modifiers": [
                         {"name": "Sos", "type": "required", "min": 1, "max": 2,
                          "options": [("Łagodny", 0), ("Ostry", 0), ("Czosnkowy", 0), ("Mieszany", 0)]},
                     ]},
                    {"name": "Falafel wrap", "desc": "Falafel, hummus, warzywa", "size": None,
                     "prices": {"wolt": 1800, "pyszne": 1900}, "modifiers": []},
                ],
            },
        ],
    },
    {
        "name": "Pad Thai Express",
        "normalized_name": "pad thai express",
        "address_street": "Mokotowska 17",
        "address_city": "Warszawa",
        "lat": 52.2240, "lng": 21.0165,
        "cuisine_tags": ["tajska", "azjatycka"],
        "image_url": "https://images.taniejjedz.pl/seed/padthai.jpg",
        "quality": 0.87,
        "platforms": [
            {"platform": "wolt", "pid": "padthai-wolt-001", "slug": "pad-thai-express", "fee": 599, "minutes": 35},
            {"platform": "pyszne", "pid": "padthai-pyszne-001", "slug": "pad-thai-express-warszawa", "fee": 699, "minutes": 40},
        ],
        "categories": [
            {
                "name": "Dania główne",
                "items": [
                    {"name": "Pad Thai z krewetkami", "desc": "Makaron ryżowy, krewetki, orzeszki", "size": None,
                     "prices": {"wolt": 3200, "pyszne": 3400}, "modifiers": [
                         {"name": "Ostrość", "type": "required", "min": 1, "max": 1,
                          "options": [("Łagodne", 0), ("Średnie", 0), ("Ostre", 0), ("Bardzo ostre", 0)]},
                     ]},
                    {"name": "Green Curry", "desc": "Zielone curry z kurczakiem i ryżem", "size": None,
                     "prices": {"wolt": 2900, "pyszne": 3100}, "modifiers": []},
                ],
            },
        ],
    },
    {
        "name": "Trattoria Napoli",
        "normalized_name": "napoli",
        "address_street": "Foksal 8",
        "address_city": "Warszawa",
        "lat": 52.2337, "lng": 21.0209,
        "cuisine_tags": ["włoska", "pasta", "pizza"],
        "image_url": "https://images.taniejjedz.pl/seed/napoli.jpg",
        "quality": 0.91,
        "platforms": [
            {"platform": "wolt", "pid": "napoli-wolt-001", "slug": "trattoria-napoli", "fee": 699, "minutes": 40},
            {"platform": "pyszne", "pid": "napoli-pyszne-001", "slug": "trattoria-napoli-warszawa", "fee": 599, "minutes": 45},
        ],
        "categories": [
            {
                "name": "Pasta",
                "items": [
                    {"name": "Spaghetti Carbonara", "desc": "Guanciale, pecorino, jajko", "size": None,
                     "prices": {"wolt": 3400, "pyszne": 3200}, "modifiers": []},
                    {"name": "Penne Arrabiata", "desc": "Pomidory, chili, czosnek", "size": None,
                     "prices": {"wolt": 2800, "pyszne": 2600}, "modifiers": []},
                ],
            },
        ],
    },
    {
        "name": "Ramen Shop",
        "normalized_name": "ramen shop",
        "address_street": "Wilcza 33",
        "address_city": "Warszawa",
        "lat": 52.2253, "lng": 21.0141,
        "cuisine_tags": ["japońska", "ramen"],
        "image_url": "https://images.taniejjedz.pl/seed/ramen.jpg",
        "quality": 0.86,
        "platforms": [
            {"platform": "wolt", "pid": "ramen-wolt-001", "slug": "ramen-shop", "fee": 699, "minutes": 40},
        ],
        "categories": [
            {
                "name": "Ramen",
                "items": [
                    {"name": "Tonkotsu Ramen", "desc": "Bulion wieprzowy, chashu, jajko, nori", "size": None,
                     "prices": {"wolt": 3600}, "modifiers": [
                         {"name": "Dodatki", "type": "optional", "min": 0, "max": 3,
                          "options": [("Extra chashu", 600), ("Extra jajko", 300), ("Extra nori", 200)]},
                     ]},
                    {"name": "Miso Ramen", "desc": "Bulion miso, tofu, warzywa", "size": None,
                     "prices": {"wolt": 3200}, "modifiers": []},
                ],
            },
        ],
    },
    {
        "name": "Pierogi Babci",
        "normalized_name": "pierogi babci",
        "address_street": "Nowogrodzka 12",
        "address_city": "Warszawa",
        "lat": 52.2270, "lng": 21.0100,
        "cuisine_tags": ["polska", "pierogi"],
        "image_url": "https://images.taniejjedz.pl/seed/pierogi.jpg",
        "quality": 0.83,
        "platforms": [
            {"platform": "pyszne", "pid": "pierogi-pyszne-001", "slug": "pierogi-babci-warszawa", "fee": 399, "minutes": 30},
        ],
        "categories": [
            {
                "name": "Pierogi",
                "items": [
                    {"name": "Pierogi ruskie 12szt", "desc": "Z ziemniakami i serem", "size": "12szt",
                     "prices": {"pyszne": 2200}, "modifiers": [
                         {"name": "Na sposób", "type": "required", "min": 1, "max": 1,
                          "options": [("Gotowane", 0), ("Smażone", 300)]},
                     ]},
                    {"name": "Pierogi z mięsem 12szt", "desc": "Z mielonym mięsem", "size": "12szt",
                     "prices": {"pyszne": 2400}, "modifiers": []},
                ],
            },
        ],
    },
    {
        "name": "Taco Loco",
        "normalized_name": "taco loco",
        "address_street": "Świętokrzyska 30",
        "address_city": "Warszawa",
        "lat": 52.2350, "lng": 21.0080,
        "cuisine_tags": ["meksykańska", "taco"],
        "image_url": "https://images.taniejjedz.pl/seed/taco.jpg",
        "quality": 0.84,
        "platforms": [
            {"platform": "wolt", "pid": "taco-wolt-001", "slug": "taco-loco", "fee": 599, "minutes": 35},
            {"platform": "pyszne", "pid": "taco-pyszne-001", "slug": "taco-loco-warszawa", "fee": 499, "minutes": 40},
        ],
        "categories": [
            {
                "name": "Taco",
                "items": [
                    {"name": "Taco al Pastor 3szt", "desc": "Wieprzowina, ananas, kolendra", "size": "3szt",
                     "prices": {"wolt": 2800, "pyszne": 2600}, "modifiers": []},
                    {"name": "Burrito wołowe", "desc": "Wołowina, ryż, fasola, guacamole", "size": None,
                     "prices": {"wolt": 3200, "pyszne": 3000}, "modifiers": []},
                ],
            },
        ],
    },
    {
        "name": "Wietnam Pho",
        "normalized_name": "wietnam pho",
        "address_street": "Hoża 25",
        "address_city": "Warszawa",
        "lat": 52.2265, "lng": 21.0150,
        "cuisine_tags": ["wietnamska", "azjatycka", "pho"],
        "image_url": "https://images.taniejjedz.pl/seed/pho.jpg",
        "quality": 0.88,
        "platforms": [
            {"platform": "wolt", "pid": "pho-wolt-001", "slug": "wietnam-pho", "fee": 599, "minutes": 40},
            {"platform": "pyszne", "pid": "pho-pyszne-001", "slug": "wietnam-pho-warszawa", "fee": 499, "minutes": 45},
        ],
        "categories": [
            {
                "name": "Zupy",
                "items": [
                    {"name": "Pho Bo", "desc": "Zupa z wołowiną i makaronem ryżowym", "size": None,
                     "prices": {"wolt": 2800, "pyszne": 2600}, "modifiers": []},
                    {"name": "Bun Bo Hue", "desc": "Pikantna zupa z Hue", "size": None,
                     "prices": {"wolt": 3000, "pyszne": 2900}, "modifiers": []},
                ],
            },
        ],
    },
    {
        "name": "Curry House",
        "normalized_name": "curry house",
        "address_street": "Koszykowa 55",
        "address_city": "Warszawa",
        "lat": 52.2220, "lng": 21.0088,
        "cuisine_tags": ["indyjska", "curry"],
        "image_url": "https://images.taniejjedz.pl/seed/curry.jpg",
        "quality": 0.85,
        "platforms": [
            {"platform": "wolt", "pid": "curry-wolt-001", "slug": "curry-house", "fee": 699, "minutes": 45},
            {"platform": "pyszne", "pid": "curry-pyszne-001", "slug": "curry-house-warszawa", "fee": 599, "minutes": 50},
        ],
        "categories": [
            {
                "name": "Curry",
                "items": [
                    {"name": "Chicken Tikka Masala", "desc": "Kurczak w kremowym sosie pomidorowym", "size": None,
                     "prices": {"wolt": 3200, "pyszne": 3000},
                     "modifiers": [
                         {"name": "Ostrość", "type": "required", "min": 1, "max": 1,
                          "options": [("Mild", 0), ("Medium", 0), ("Hot", 0)]},
                     ]},
                    {"name": "Naan czosnkowy", "desc": "Pieczywo naan z czosnkiem", "size": None,
                     "prices": {"wolt": 800, "pyszne": 700}, "modifiers": []},
                ],
            },
        ],
    },
    {
        "name": "Falafel King",
        "normalized_name": "falafel king",
        "address_street": "Bracka 16",
        "address_city": "Warszawa",
        "lat": 52.2310, "lng": 21.0130,
        "cuisine_tags": ["bliskowschodnia", "falafel", "wegańska"],
        "image_url": "https://images.taniejjedz.pl/seed/falafel.jpg",
        "quality": 0.82,
        "platforms": [
            {"platform": "wolt", "pid": "falafel-wolt-001", "slug": "falafel-king", "fee": 499, "minutes": 30},
            {"platform": "pyszne", "pid": "falafel-pyszne-001", "slug": "falafel-king-warszawa", "fee": 399, "minutes": 35},
        ],
        "categories": [
            {
                "name": "Główne",
                "items": [
                    {"name": "Falafel Plate", "desc": "Falafel, hummus, sałatki, pita", "size": None,
                     "prices": {"wolt": 2600, "pyszne": 2400}, "modifiers": []},
                    {"name": "Shakshuka", "desc": "Jajka w sosie pomidorowym z przyprawami", "size": None,
                     "prices": {"wolt": 2400, "pyszne": 2200}, "modifiers": []},
                ],
            },
        ],
    },
]


async def seed() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # ── Check if already seeded ─────────────────────────
        from sqlalchemy import select, func
        count = (await session.execute(select(func.count()).select_from(CanonicalRestaurant))).scalar()
        if count and count > 0:
            print(f"Database already has {count} restaurants. Skipping seed.")
            await engine.dispose()
            return

        # ── City ────────────────────────────────────────────
        city = City(
            name="Warszawa",
            slug="warszawa",
            center_lat=52.2297,
            center_lng=21.0122,
            radius_km=15,
            is_active=True,
        )
        session.add(city)
        await session.flush()

        # ── Restaurants ─────────────────────────────────────
        for rdata in RESTAURANTS:
            restaurant = CanonicalRestaurant(
                city_id=city.id,
                name=rdata["name"],
                normalized_name=rdata["normalized_name"],
                address_street=rdata["address_street"],
                address_city=rdata["address_city"],
                latitude=rdata["lat"],
                longitude=rdata["lng"],
                cuisine_tags=rdata["cuisine_tags"],
                image_url=rdata["image_url"],
                data_quality_score=rdata["quality"],
                is_active=True,
            )
            session.add(restaurant)
            await session.flush()

            # ── Platform restaurants ────────────────────────
            platform_map: dict[str, PlatformRestaurant] = {}
            for pdata in rdata["platforms"]:
                pr = PlatformRestaurant(
                    canonical_restaurant_id=restaurant.id,
                    platform=pdata["platform"],
                    platform_restaurant_id=pdata["pid"],
                    platform_name=rdata["name"],
                    platform_slug=pdata["slug"],
                    platform_url=None,
                    latitude=rdata["lat"],
                    longitude=rdata["lng"],
                    match_confidence=1.0,
                    is_active=True,
                    last_scraped_at=now,
                )
                session.add(pr)
                await session.flush()
                platform_map[pdata["platform"]] = pr

                # Operating hours (Mon-Sun 10:00-23:00)
                for day in range(7):
                    session.add(OperatingHours(
                        platform_restaurant_id=pr.id,
                        day_of_week=day,
                        open_time=time(10, 0),
                        close_time=time(23, 0),
                        is_closed=False,
                    ))

                # Delivery fee
                session.add(DeliveryFee(
                    platform_restaurant_id=pr.id,
                    geohash="u3qcn",
                    fee_grosz=pdata["fee"],
                    min_order_grosz=3000,
                    estimated_minutes=pdata["minutes"],
                    free_delivery_above_grosz=8000,
                    fetched_at=now,
                ))

            # ── Categories + menu items ─────────────────────
            for sort_idx, cdata in enumerate(rdata["categories"]):
                category = MenuCategory(
                    canonical_restaurant_id=restaurant.id,
                    name=cdata["name"],
                    sort_order=sort_idx,
                )
                session.add(category)
                await session.flush()

                for item_data in cdata["items"]:
                    cmi = CanonicalMenuItem(
                        canonical_restaurant_id=restaurant.id,
                        category_id=category.id,
                        name=item_data["name"],
                        normalized_name=item_data["name"].lower(),
                        description=item_data["desc"],
                        size_label=item_data.get("size"),
                    )
                    session.add(cmi)
                    await session.flush()

                    # Platform menu items + modifiers
                    for platform_key, price in item_data["prices"].items():
                        pr = platform_map.get(platform_key)
                        if pr is None:
                            continue

                        pmi = PlatformMenuItem(
                            canonical_menu_item_id=cmi.id,
                            platform_restaurant_id=pr.id,
                            platform_item_id=f"{platform_key}-{cmi.id.hex[:8]}",
                            platform_name=item_data["name"],
                            price_grosz=price,
                            match_confidence=1.0,
                            is_available=True,
                            last_scraped_at=now,
                        )
                        session.add(pmi)
                        await session.flush()

                        # Modifier groups + options
                        for mg_idx, mg_data in enumerate(item_data.get("modifiers", [])):
                            mg = ModifierGroup(
                                platform_menu_item_id=pmi.id,
                                name=mg_data["name"],
                                group_type=mg_data["type"],
                                min_selections=mg_data["min"],
                                max_selections=mg_data["max"],
                                sort_order=mg_idx,
                                platform_group_id=f"{platform_key}-grp-{mg_idx}",
                            )
                            session.add(mg)
                            await session.flush()

                            for opt_name, opt_price in mg_data["options"]:
                                session.add(ModifierOption(
                                    modifier_group_id=mg.id,
                                    name=opt_name,
                                    normalized_name=opt_name.lower(),
                                    price_grosz=opt_price,
                                    is_default=False,
                                    is_available=True,
                                    platform_option_id=f"{platform_key}-opt-{opt_name[:8].lower()}",
                                ))

        # ── Feature flags ───────────────────────────────────
        session.add(FeatureFlag(key="city.warszawa.enabled", config={"city": "warszawa"}, is_active=True))
        session.add(FeatureFlag(key="comparison.enabled", config={}, is_active=True))

        await session.commit()

    await engine.dispose()
    print(f"Seeded {len(RESTAURANTS)} restaurants in Warszawa with menus, modifiers, and delivery fees.")


if __name__ == "__main__":
    asyncio.run(seed())
