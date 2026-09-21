# Biblioteka Polska w Paryżu – zbiory cyfrowe (pilot)

Wyszukiwanie i przeglądanie obiektów, skany IIIF (Mirador), metadane jako Linked Open Data, graf i SPARQL.

**Demo:** https://patthub.github.io/ibpp_pilot/

## Jak to działa

- `build.py` – CSV z katalogowania + `scans/<sygnatura>/*.jpg` → `docs/data/objects.ttl` (schema.org) i statyczne IIIF (kafle level 0 + manifest v3) w `docs/iiif/`.
- `docs/` – statyczny (GitHub Pages serwuje ten katalog z gałęzi `main`) front bez kroku budowania. `sparql-local.js` uruchamia Oxigraph (WASM) w przeglądarce, więc SPARQL działa też na GitHub Pages.
- `server.py` – docelowy serwer LOD na własną domenę: endpoint `/sparql`, URI `/id/…` z content negotiation (Turtle / JSON-LD / RDF/XML, HTML przez 303).

## Aktualizacja danych

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
brew install vips                       # cięcie kafli IIIF
.venv/bin/python build.py "plik.csv"    # CSV i scans/ nie trafiają do repo
git add docs && git commit -m "dane" && git push   # Pages publikuje docs/ po pushu
```

Podgląd lokalny: `python3 -m http.server -d docs` albo `.venv/bin/python server.py`.

Po zmianie `style.css`, `app.js` lub `sparql-local.js` podbij `?v=` w odnośnikach w `docs/*.html` (GitHub Pages trzyma pliki w cache 10 min).
