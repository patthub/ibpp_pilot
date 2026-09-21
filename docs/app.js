// Wspólne pomocniki dla wszystkich stron.
const BASE = "https://data.bpp.example/id/"; // = BASE w server.py

const PREFIXES = {
  schema: "http://schema.org/",
  rdf: "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
  rdfs: "http://www.w3.org/2000/01/rdf-schema#",
  owl: "http://www.w3.org/2002/07/owl#",
  dcterms: "http://purl.org/dc/terms/",
  skos: "http://www.w3.org/2004/02/skos/core#",
  wd: "http://www.wikidata.org/entity/",
  bpp: BASE,
};
const SPARQL_PREFIXES = Object.entries(PREFIXES).map(([p, u]) => `PREFIX ${p}: <${u}>`).join("\n");
// etykieta = pierwsza dostępna z tych właściwości
const LABEL = "(schema:name|rdfs:label|skos:prefLabel|dcterms:title)";
// wzorzec SPARQL: ?out = etykieta ?s po polsku, a gdy brak – dowolna, a gdy brak – sygnatura
const labelOf = (s, out) => `
  OPTIONAL { ${s} ${LABEL} ?${out}_pl FILTER(LANGMATCHES(LANG(?${out}_pl), "pl")) }
  OPTIONAL { ${s} ${LABEL} ?${out}_any }
  OPTIONAL { ${s} schema:identifier ?${out}_id }
  BIND(COALESCE(?${out}_pl, ?${out}_any, ?${out}_id) AS ?${out})`;

async function sparql(query) {
  const r = await fetch("sparql", {
    method: "POST",
    headers: { "Content-Type": "application/sparql-query", Accept: "application/sparql-results+json" },
    body: SPARQL_PREFIXES + "\n" + query,
  });
  if (!r.ok) throw new Error(await r.text());
  // wiersze jako {zmienna: wartość, zmienna_lang: "pl"}
  return (await r.json()).results.bindings.map(b =>
    Object.fromEntries(Object.entries(b).flatMap(([k, v]) => [[k, v.value], ...(v["xml:lang"] ? [[k + "_lang", v["xml:lang"]]] : [])])));
}

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`);
// zapis prefiksowany do wyświetlania, np. schema:name
const curie = u => { for (const [p, ns] of Object.entries(PREFIXES)) if (u.startsWith(ns)) return `${p}:${u.slice(ns.length)}`; return u; };
// URI z naszej przestrzeni → strona zasobu, inne zostają zewnętrzne
const href = u => (u.startsWith(BASE) ? "resource.html?id=" + encodeURIComponent(u.slice(BASE.length)) : u);
const link = (u, text) => `<a href="${esc(href(u))}"${u.startsWith(BASE) ? "" : ' target="_blank" rel="noopener"'}>${esc(text || curie(u))}</a>`;
