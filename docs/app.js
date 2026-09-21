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

// --- prezentacja ---

// etykiety pól (predykat → nazwa po polsku); kolejność = kolejność w opisie obiektu
const FIELDS = {
  "schema:creator": "Twórca",
  "schema:dateCreated": "Data powstania",
  "schema:temporal": "Datowanie",
  "schema:locationCreated": "Miejsce powstania",
  "schema:artform": "Rodzaj",
  "schema:material": "Materiał",
  "schema:artMedium": "Technika",
  "schema:height": "Wysokość",
  "schema:width": "Szerokość",
  "schema:depth": "Głębokość",
  "schema:about": "Temat",
  "schema:keywords": "Słowa kluczowe",
  "schema:alternateName": "Inne tytuły",
  "schema:isPartOf": "Kolekcja",
  "schema:identifier": "Sygnatura",
  "schema:holdingArchive": "Właściciel",
  "schema:provider": "Udostępnia",
  "schema:license": "Prawa",
  "owl:sameAs": "Zobacz też",
};
// relacje odwrotne: kto wskazuje na ten zasób → nagłówek sekcji
const INVERSE = {
  "schema:creator": "Dzieła",
  "schema:about": "Obiekty na ten temat",
  "schema:isPartOf": "Obiekty w kolekcji",
  "schema:locationCreated": "Powstałe w tym miejscu",
  "schema:holdingArchive": "Obiekty w zbiorach",
  "schema:provider": "Udostępniane obiekty",
};
const TYPES = {
  "schema:Sculpture": "Rzeźba", "schema:Painting": "Obraz", "schema:Photograph": "Fotografia",
  "schema:Manuscript": "Rękopis", "schema:Book": "Książka", "schema:Map": "Mapa", "schema:CreativeWork": "Obiekt",
  "schema:Person": "Osoba", "schema:Place": "Miejsce", "schema:Organization": "Instytucja",
  "schema:Collection": "Kolekcja", "schema:Thing": "Temat",
};
const typeLabel = t => TYPES[curie(t)] || curie(t);

// z wierszy z wartościami w wielu językach zostaw jeden język: pl → en → pierwszy
const LANG_ORDER = ["pl", "en"];
function pickLang(rows, key = "o") {
  const langs = rows.map(r => r[key + "_lang"]).filter(Boolean);
  const lang = LANG_ORDER.find(l => langs.includes(l)) || langs[0];
  return rows.filter(r => !r[key + "_lang"] || r[key + "_lang"] === lang);
}

// 1 obiekt, 2 obiekty, 5 obiektów, 22 obiekty
const plural = (n, one, few, many) =>
  n === 1 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? few : many;

// zewnętrzne źródła po nazwie zamiast gołego URL
const SOURCES = { "wikidata.org": "Wikidata", "viaf.org": "VIAF", "id.loc.gov": "Library of Congress", "data.bnf.fr": "BnF" };
const sourceName = u => Object.entries(SOURCES).find(([host]) => u.includes(host))?.[1] || new URL(u).host;

const NO_SCAN = `<span class="no-scan"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/></svg>Skan w przygotowaniu</span>`;
// karta obiektu w siatce (wyniki, dzieła autora…)
const card = r => `
  <li class="card">
    <a href="${esc(href(r.s))}">
      <div class="card-img">${r.thumb ? `<img src="${esc(r.thumb)}" alt="" loading="lazy">` : NO_SCAN}</div>
      <div class="card-body">
        ${r.type ? `<p class="kicker">${esc(typeLabel(r.type))}</p>` : ""}
        <h3>${esc(r.label)}</h3>
        <p class="muted">${esc([r.creator, r.date].filter(Boolean).join(" · "))}</p>
      </div>
    </a>
  </li>`;
// kolumny SPARQL potrzebne karcie: ?s ?label ?type ?thumb ?creator ?date ?id (z GROUP BY ?s)
const CARD_VARS = `(SAMPLE(?lbl) AS ?label) (SAMPLE(?t) AS ?type) (SAMPLE(?th) AS ?thumb) (SAMPLE(?c) AS ?creator) (SAMPLE(?d) AS ?date) (SAMPLE(?ident) AS ?id)`;
const CARD_WHERE = `
  OPTIONAL { ?s a ?t }
  ${labelOf("?s", "lbl")}
  OPTIONAL { ?s schema:thumbnailUrl ?th }
  OPTIONAL { ?s schema:creator ?cr ${labelOf("?cr", "c")} }
  OPTIONAL { ?s schema:dateCreated ?d }
  OPTIONAL { ?s schema:identifier ?ident }`;
