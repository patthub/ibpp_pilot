// SPARQL w przeglądarce (Oxigraph WASM) – GitHub Pages nie ma serwera.
// Przechwytuje fetch do „…/sparql” (app.js, Yasgui) i odpowiada z lokalnego store'a z data/objects.ttl.
// ponytail: cały graf ładowany do przeglądarki; przy dużych zbiorach → prawdziwy endpoint (server.py / Oxigraph) i usunąć ten plik
(() => {
  const realFetch = window.fetch.bind(window);
  const storeReady = (async () => {
    const ox = await import("https://cdn.jsdelivr.net/npm/oxigraph@0.5.11/web.js");
    await ox.default();
    const store = new ox.Store();
    store.load(await (await realFetch("data/objects.ttl")).text(), { format: "text/turtle" });
    return store;
  })();

  window.fetch = async (input, init) => {
    const req = new Request(input, init);
    const url = new URL(req.url);
    if (url.origin !== location.origin || !url.pathname.endsWith("/sparql")) return realFetch(input, init);

    const body = req.method === "POST" ? await req.text() : "";
    const query = (req.headers.get("Content-Type") || "").startsWith("application/sparql-query")
      ? body
      : new URLSearchParams(body).get("query") || url.searchParams.get("query");
    const accept = req.headers.get("Accept") || "";
    const store = await storeReady;
    const pick = list => list.find(f => accept.includes(f)) || list.at(-1);
    const run = fmt => new Response(store.query(query, { results_format: fmt }), { headers: { "Content-Type": fmt } });
    try {
      // SELECT/ASK → wyniki SPARQL; Oxigraph odrzuca ten format dla CONSTRUCT/DESCRIBE → wtedy RDF. UPDATE rzuca błąd – tylko odczyt
      try {
        return run(pick(["text/csv", "text/tab-separated-values", "application/sparql-results+xml", "application/sparql-results+json"]));
      } catch (e) {
        if (!/RDF format/.test(e.message || e)) throw e;
        return run(pick(["application/ld+json", "application/n-triples", "application/rdf+xml", "text/turtle"]));
      }
    } catch (e) {
      return new Response(String(e.message || e), { status: 400, headers: { "Content-Type": "text/plain" } });
    }
  };
})();
