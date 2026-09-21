"""Biblioteka cyfrowa BPP: pliki statyczne + SPARQL + dereferencja URI /id/…

Uruchom:  .venv/bin/python server.py   → http://localhost:8000
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from pyoxigraph import BlankNode, NamedNode, QueryBoolean, QueryResultsFormat, QuerySolutions, RdfFormat, Store, serialize

# ponytail: domena-zaślepka; musi się zgadzać z BASE w docs/app.js i build.py
BASE = "https://data.bpp.example/id/"
ROOT = Path(__file__).parent
WEB = ROOT / "docs"
PORT = 8000

# ponytail: store w pamięci, wczytywany przy starcie; Store("db/") gdy danych będzie za dużo na RAM
store = Store()
for f in sorted((WEB / "data").glob("*.ttl")):
    store.load(path=f, format=RdfFormat.TURTLE)
print(f"{len(store)} trójek z docs/data/*.ttl")

RDF_TYPES = {  # rozszerzenie / Accept → format
    ".ttl": ("text/turtle", RdfFormat.TURTLE),
    ".jsonld": ("application/ld+json", RdfFormat.JSON_LD),
    ".nt": ("application/n-triples", RdfFormat.N_TRIPLES),
    ".rdf": ("application/rdf+xml", RdfFormat.RDF_XML),
}


def rdf_from_accept(accept):
    for mime, fmt in RDF_TYPES.values():
        if mime in accept:
            return mime, fmt
    return None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def send(self, code, ctype, body):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")  # otwarty endpoint LOD
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/sparql":
            return self.sparql(parse_qs(url.query).get("query", [""])[0])
        if url.path.startswith("/id/"):
            return self.resource(unquote(url.path[4:]))
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/sparql":
            return self.send(404, "text/plain", "not found")
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        if self.headers.get("Content-Type", "").startswith("application/sparql-query"):
            return self.sparql(body)
        return self.sparql(parse_qs(body).get("query", [""])[0])

    def sparql(self, query):
        # ponytail: brak limitu czasu zapytania; przed publicznym wystawieniem → oxigraph server z timeoutem albo proxy
        if not query:
            return self.send(400, "text/plain", "brak parametru query")
        try:
            res = store.query(query)  # tylko zapytania; UPDATE nie przechodzi przez query()
        except (SyntaxError, ValueError, OSError) as e:
            return self.send(400, "text/plain", str(e))
        accept = self.headers.get("Accept", "")
        if isinstance(res, (QuerySolutions, QueryBoolean)):
            if "text/csv" in accept:
                return self.send(200, "text/csv", res.serialize(format=QueryResultsFormat.CSV))
            return self.send(200, "application/sparql-results+json", res.serialize(format=QueryResultsFormat.JSON))
        mime, fmt = rdf_from_accept(accept) or RDF_TYPES[".ttl"]
        return self.send(200, mime, res.serialize(format=fmt))

    def resource(self, local):
        # /id/X.ttl itd. wymusza format; bez rozszerzenia decyduje Accept (przeglądarka → HTML)
        suffix = Path(local).suffix
        neg = RDF_TYPES.get(suffix)
        if neg:
            local = local[: -len(suffix)]
        else:
            neg = rdf_from_accept(self.headers.get("Accept", ""))
        if not neg:
            # 303 na stronę HTML (wzorzec LOD „303 See Other”); ta sama strona działa na GitHub Pages
            self.send_response(303)
            self.send_header("Location", "/resource.html?id=" + quote(local, safe=""))
            self.end_headers()
            return
        try:
            node = NamedNode(BASE + local)  # waliduje IRI; nic z URL nie trafia do tekstu zapytania
        except ValueError:
            return self.send(404, "text/plain", "niepoprawny identyfikator")
        # CBD-lite: trójki zasobu + jego węzły puste (jeden poziom)
        triples = [q.triple for q in store.quads_for_pattern(node, None, None)]
        for t in list(triples):
            if isinstance(t.object, BlankNode):
                triples += [q.triple for q in store.quads_for_pattern(t.object, None, None)]
        if not triples:
            return self.send(404, "text/plain", f"brak zasobu {node.value}")
        mime, fmt = neg
        return self.send(200, mime, serialize(triples, format=fmt))


if __name__ == "__main__":
    print(f"http://localhost:{PORT}")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
