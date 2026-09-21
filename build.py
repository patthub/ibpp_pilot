"""CSV + skany → docs/data/objects.ttl + statyczne IIIF w docs/iiif/.

  .venv/bin/python build.py "Bolesław Biegas - pilot.csv"

Skany: scans/<identifier>/*.jpg|tif (kolejność alfabetyczna = kolejność ujęć).
Kafle IIIF (level 0) robi libvips: `brew install vips` / `apt install libvips-tools`.
"""
import csv
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from pyoxigraph import Literal, NamedNode, RdfFormat, Triple, serialize

BASE = "https://data.bpp.example/id/"  # = BASE w server.py
# ponytail: adres, pod którym serwowane są kafle; id jest wpisane w info.json, więc zmiana adresu = usuń docs/iiif i przebuduj
IIIF_BASE = "https://patthub.github.io/ibpp_pilot/iiif/"
ROOT = Path(__file__).parent
OUT_TTL = ROOT / "docs" / "data" / "objects.ttl"
IIIF_DIR = ROOT / "docs" / "iiif"
SCANS = ROOT / "scans"

S, OWL, RDF = "http://schema.org/", "http://www.w3.org/2002/07/owl#", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XSD = "http://www.w3.org/2001/XMLSchema#"
LANGS = ("PL", "EN", "FR")
# objectType_EN → klasa schema.org; ponytail: dopisywać przy nowych typach, reszta = CreativeWork
TYPES = {"Sculpture": "Sculpture", "Painting": "Painting", "Photograph": "Photograph", "Manuscript": "Manuscript", "Book": "Book", "Map": "Map"}
# dane robocze / magazynowe, świadomie niepublikowane
INTERNAL = {"No", "masterFile", "accessFile", "digitisationDate", "operator", "notes", "currentLocation_dates",
            *(f"{c}_{L}" for c in ("workflowStatus", "location", "currentLocation") for L in LANGS)}

triples = {}  # dict jako uporządkowany set


def add(s, p, o):
    triples[Triple(s, NamedNode(p), o)] = None


def slug(s):
    s = unicodedata.normalize("NFKD", s.replace("ł", "l").replace("Ł", "L")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def ext_uri(v):
    """Q123 / pełny URL → NamedNode, puste → None."""
    v = v.strip()
    if re.fullmatch(r"Q\d+", v):
        return NamedNode("http://www.wikidata.org/entity/" + v)
    return NamedNode(v) if v.startswith("http") else None


def entity(path, cls, labels, same_as=()):
    """Lokalny węzeł (osoba, miejsce, temat…) z etykietami w językach; wspólny dla wszystkich rekordów."""
    n = NamedNode(BASE + path)
    add(n, RDF + "type", NamedNode(S + cls))
    for lang, v in labels:
        add(n, S + "name", Literal(v, language=lang))
    for u in same_as:
        add(n, OWL + "sameAs", u)
    return n


def build_row(r):
    ident = r["identifier"].strip()
    obj = NamedNode(BASE + ident)
    used = set(INTERNAL)

    def col(name):
        used.add(name)
        return (r.get(name) or "").strip()

    def langs(stem):
        return [(L.lower(), v) for L in LANGS if (v := col(f"{stem}_{L}"))]

    def literals(prop, stem):
        for lang, v in langs(stem):
            add(obj, S + prop, Literal(v, language=lang))

    def key(stem):  # klucz węzła: EN, a gdy brak – PL
        lab = langs(stem)
        return slug(dict(lab).get("en") or lab[0][1]) if lab else None

    col("identifier")
    add(obj, S + "identifier", Literal(ident))
    if rid := col("recordID"):
        add(obj, S + "identifier", Literal(rid))

    add(obj, RDF + "type", NamedNode(S + TYPES.get(dict(langs("objectType")).get("en", ""), "CreativeWork")))
    literals("artform", "objectType")
    literals("name", "title")
    literals("alternateName", "alternativeTitle")
    literals("description", "description")
    literals("material", "material")
    literals("artMedium", "technique")  # ponytail: schema.org nie ma „techniki”; CIDOC/Linked Art gdy potrzebna precyzja
    for lang, v in langs("keyword"):
        for kw in filter(None, map(str.strip, re.split(r"[|;]", v))):
            add(obj, S + "keywords", Literal(kw, language=lang))

    if k := key("collection"):
        add(obj, S + "isPartOf", entity(f"collection/{k}", "Collection", langs("collection")))
    if k := key("subject"):
        add(obj, S + "about", entity(f"subject/{k}", "Thing", langs("subject")))

    creator_uri = ext_uri(col("creator_URI"))
    viaf = col("VIAF")
    if creator_uri or langs("creator_Label"):
        same = [u for u in (creator_uri, viaf and NamedNode("http://viaf.org/viaf/" + viaf)) if u]
        path = "agent/" + (creator_uri.value.rsplit("/", 1)[-1] if creator_uri else key("creator_Label"))
        add(obj, S + "creator", entity(path, "Person", langs("creator_Label"), same))

    place_uri = ext_uri(col("placeCreated_URI"))
    if place_uri or langs("placeCreated"):
        path = "place/" + (place_uri.value.rsplit("/", 1)[-1] if place_uri else key("placeCreated"))
        add(obj, S + "locationCreated", entity(path, "Place", langs("placeCreated"), [place_uri] if place_uri else []))

    if d := col("dateCreated"):
        add(obj, S + "dateCreated", Literal(d, datatype=NamedNode(XSD + "gYear")) if re.fullmatch(r"\d{4}", d) else Literal(d))
    if d := col("displayDate"):
        add(obj, S + "temporal", Literal(d))

    for dim in ("height", "width", "depth"):
        if v := col(f"{dim}_cm"):
            # ponytail: literał „55 cm”; QuantitativeValue, gdy ktoś zechce liczyć po wymiarach w SPARQL
            add(obj, S + dim, Literal(v.replace(",", ".") + " cm"))

    if k := key("provider"):
        add(obj, S + "provider", entity(f"org/{k}", "Organization", langs("provider")))
    if v := col("owner"):
        add(obj, S + "holdingArchive", entity(f"org/{slug(v)}", "Organization", []))

    lic = ext_uri(col("rightsStatus_URI"))
    lic_label = col("rightsStatus_Label") or col("license")
    col("license")
    if lic or lic_label:
        add(obj, S + "license", lic or Literal(lic_label))

    # nic nie ginie po cichu: niezmapowane, niepuste kolumny → ostrzeżenie
    for c, v in r.items():
        if c not in used and (v or "").strip():
            print(f"  ! {ident}: pominięta kolumna {c!r} = {v.strip()[:40]!r}", file=sys.stderr)

    title = dict(langs("title"))
    iiif(ident, obj, title.get("pl") or next(iter(title.values()), ident))


def iiif(ident, obj, label):
    images = sorted(p for p in (SCANS / ident).glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".tif", ".tiff", ".png"})
    if not images:
        return
    out = IIIF_DIR / ident
    base = IIIF_BASE + ident
    canvases = []
    for i, img in enumerate(images, 1):
        tiles = out / img.stem
        if not (tiles / "info.json").exists():  # kafle już są → nie tniemy ponownie
            out.mkdir(parents=True, exist_ok=True)
            subprocess.run(["vips", "dzsave", img, tiles, "--layout", "iiif3", "--id", base, "--tile-size", "512"], check=True)
            (out / "vips-properties.xml").unlink(missing_ok=True)  # techniczne metadane vips, niepotrzebne w IIIF
        info = json.loads((tiles / "info.json").read_text())
        w, h, svc = info["width"], info["height"], info["id"]
        fw, fh = map(int, next((tiles / "full").iterdir()).name.split(","))
        cid = f"{base}/canvas/{i}"
        canvases.append({
            "id": cid, "type": "Canvas", "label": {"none": [img.stem]}, "width": w, "height": h,
            "items": [{"id": f"{cid}/page", "type": "AnnotationPage", "items": [{
                "id": f"{cid}/page/image", "type": "Annotation", "motivation": "painting", "target": cid,
                # level 0 ma tylko pomniejszony „full” wygenerowany przez vips; pełną rozdzielczość dają kafle z service
                "body": {"id": f"{svc}/full/{fw},{fh}/0/default.jpg", "type": "Image", "format": "image/jpeg", "width": fw, "height": fh,
                         "service": [{"id": svc, "type": "ImageService3", "profile": "level0"}]},
            }]}],
        })
    thumb = out / "thumb.jpg"
    if not thumb.exists():
        subprocess.run(["vipsthumbnail", images[0], "--size", "400", "-o", str(thumb)], check=True)
    manifest = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": f"{base}/manifest.json", "type": "Manifest",
        "label": {"pl": [label]},
        "homepage": [{"id": obj.value, "type": "Text", "label": {"pl": ["Rekord w katalogu"]}, "format": "text/html"}],
        "seeAlso": [{"id": obj.value + ".ttl", "type": "Dataset", "format": "text/turtle"}],
        "thumbnail": [{"id": f"{base}/thumb.jpg", "type": "Image", "format": "image/jpeg"}],
        "items": canvases,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    add(obj, S + "associatedMedia", NamedNode(manifest["id"]))
    add(obj, S + "thumbnailUrl", NamedNode(f"{base}/thumb.jpg"))
    print(f"  IIIF {ident}: {len(images)} skan(y)")


if __name__ == "__main__":
    with open(sys.argv[1], newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("identifier") or "").strip()]
    for r in rows:
        build_row(r)
    ttl = serialize(triples, format=RdfFormat.TURTLE, prefixes={
        "schema": S, "owl": OWL, "xsd": XSD, "wd": "http://www.wikidata.org/entity/", "bpp": BASE})
    OUT_TTL.write_bytes("# WYGENEROWANE przez build.py – nie edytuj ręcznie\n".encode() + ttl)
    print(f"{len(rows)} rekordów, {len(triples)} trójek → {OUT_TTL.relative_to(ROOT)}")
