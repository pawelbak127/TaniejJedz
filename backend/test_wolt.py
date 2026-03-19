import httpx
import asyncio
import json

async def test_glovo_recon():
    # Glovo WYMAGA dobrych nagłówków, inaczej dostaniesz 403 od razu
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "glovo-language": "pl",
        "glovo-app-platform": "web",
    }

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        print("--- TEST 1: WYSZUKIWANIE (GLOVO DISCOVERY) ---")
        # Wrocław, Rynek
        lat, lon = "51.1100", "17.0300"
        
        # Endpoint wyszukiwania dla Glovo
        search_url = f"https://api.glovoapp.com/v3/stores?lat={lat}&lon={lon}&category=RESTAURANT"
        
        try:
            response = await client.get(search_url)
            print(f"Status HTTP (Search): {response.status_code}")
            
            store_id = None
            if response.status_code == 200:
                data = response.json()
                # Szukamy pierwszej lepszej restauracji (np. McDonald's)
                for store in data.get('stores', []):
                    if "McDonald" in store.get('name', ''):
                        print(f"Znaleziono: {store.get('name')}")
                        store_id = store.get('id')
                        print(f"Store ID: {store_id}")
                        break
                
                if not store_id and data.get('stores'):
                    first_store = data['stores'][0]
                    print(f"Nie znaleziono Maka, biorę: {first_store.get('name')}")
                    store_id = first_store.get('id')
            else:
                print(f"Błąd wyszukiwania: {response.text[:200]}")
                return

            if not store_id:
                print("Nie znaleziono żadnego sklepu.")
                return

            print(f"\n--- TEST 2: POBIERANIE MENU (GLOVO STORE API) ---")
            # Endpoint menu dla Glovo
            menu_url = f"https://api.glovoapp.com/chapi/v1/stores/{store_id}/products"
            print(f"Pobieram: {menu_url}")
            
            menu_resp = await client.get(menu_url)
            print(f"Status HTTP (Menu): {menu_resp.status_code}")
            
            if menu_resp.status_code == 200:
                menu_data = menu_resp.json()
                # Glovo dzieli menu na 'categories'
                categories = menu_data.get('categories', [])
                print(f"✅ Sukces! Znaleziono {len(categories)} kategorii.")
                
                if categories:
                    first_cat = categories[0]
                    products = first_cat.get('products', [])
                    print(f"Kategoria: {first_cat.get('name')} ma {len(products)} produktów.")
                    
                    if products:
                        prod = products[0]
                        print(f"\nPrzykładowy produkt: {prod.get('name')}")
                        print(f"Cena: {prod.get('price')} (Sprawdźmy czy to grosze!)")
                        
                        # Sprawdzamy dodatki (w Glovo nazywają się 'attributes' lub 'modifiers')
                        # Często są wewnątrz obiektu produktu
                        print(f"Klucze produktu: {list(prod.keys())}")
            else:
                print(f"Błąd Menu: {menu_resp.status_code}")

        except Exception as e:
            print(f"Wystąpił błąd: {e}")

if __name__ == "__main__":
    asyncio.run(test_glovo_recon())