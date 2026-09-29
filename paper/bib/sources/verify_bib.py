"""Cross-check titles and author lists in paper/bib/part_a.bib against fetched source records."""
import json, re, sys, unicodedata
B = sys.argv[1]; SRC = sys.argv[2]

def latex_to_text(s):
    s = s.replace(r"{\c{c}}", "ç").replace(r"{\'e}", "é").replace(r"\'e", "é")
    s = re.sub(r"[{}]", "", s)
    return re.sub(r"\s+", " ", s).strip()

def norm(s):
    s = unicodedata.normalize("NFKD", latex_to_text(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()

def parse_bib(text):
    entries = {}
    for m in re.finditer(r"@(\w+)\{([^,]+),(.*?)\n\}", text, re.S):
        typ, key, body = m.groups()
        fields = {}
        for fm in re.finditer(r'(\w+)\s*=\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}|"[^"]*"|\w+)', body):
            v = fm.group(2)
            if v.startswith("{") or v.startswith('"'): v = v[1:-1]
            fields[fm.group(1).lower()] = re.sub(r"\s+", " ", v).strip()
        entries[key] = (typ, fields)
    return entries

def names(authorfield):
    out = []
    for a in re.split(r"\s+and\s+", authorfield):
        a = a.strip()
        if "," in a:
            last, first = [x.strip() for x in a.split(",", 1)]
            a = f"{first} {last}"
        out.append(norm(a))
    return out

def bib_names_from_source(path):
    t = open(path, encoding="utf-8").read()
    e = parse_bib(t.replace("\n}", "\n}\n"))
    (typ, f), = e.values()
    return f["title"], names(f["author"])

mine = parse_bib(open(B, encoding="utf-8").read())
checks = {
 "froger2026gaia2": ("arxiv", f"{SRC}/arxiv_2602.11964.bib"),
 "li2026beyond": ("arxiv", f"{SRC}/arxiv_2603.09337.bib"),
 "li2026never": ("arxiv", f"{SRC}/arxiv_2609.17416.bib"),
 "lin2024streamingbench": ("arxiv", f"{SRC}/arxiv_2411.03628.bib"),
 "liu2026streammembench": ("arxiv", f"{SRC}/arxiv_2606.14571.bib"),
 "dhanda2026deltalogic": ("arxiv", f"{SRC}/arxiv_2604.02733.bib"),
 "chakrabarti2025cope": ("arxiv", f"{SRC}/arxiv_2512.18027.bib"),
 "cheng2026your": ("acl", f"{SRC}/acl_2026.findings-acl.1848.bib"),
 "ding2026proactor": ("acl", f"{SRC}/acl_2026.acl-long.832.bib"),
 "wilie2024belief": ("acl", f"{SRC}/acl_2024.emnlp-main.586.bib"),
 "kang2025win": ("neurips", f"{SRC}/neurips_winfast.bib"),
}
ok = True
for key, (kind, path) in checks.items():
    typ, f = mine[key]
    st, sa = bib_names_from_source(path)
    t_ok = norm(f["title"]) == norm(st)
    a_ok = names(f["author"]) == sa
    ok &= t_ok and a_ok
    print(f"{key:24s} src={kind:7s} title_match={t_ok} authors_match={a_ok} n_authors={len(sa)}")
    if not a_ok:
        print("   mine:", names(f["author"])); print("   src :", sa)
    if not t_ok:
        print("   mine:", norm(f["title"])); print("   src :", norm(st))
# Crossref record for the ICASSP version
cr = json.load(open(f"{SRC}/crossref_sb_doi.json"))["message"]
typ, f = mine["lin2026streamingbench"]
cr_auth = [norm(a["given"] + " " + a["family"]) for a in cr["author"]]
t_ok = norm(f["title"]) == norm(cr["title"][0]); a_ok = names(f["author"]) == cr_auth
d_ok = f["doi"].lower() == cr["DOI"].lower(); p_ok = f["pages"].replace("--", "-") == cr["page"]
ok &= a_ok and d_ok and p_ok
print(f"{'lin2026streamingbench':24s} src=crossref title_match={t_ok} (case-insensitive; IEEE casing 'Streamingbench') authors_match={a_ok} n_authors={len(cr_auth)} doi_match={d_ok} pages_match={p_ok}")
# DOIs of ACL/NeurIPS entries vs source exports
for key, path in [("cheng2026your", "acl_2026.findings-acl.1848.bib"), ("ding2026proactor", "acl_2026.acl-long.832.bib"), ("wilie2024belief", "acl_2024.emnlp-main.586.bib"), ("kang2025win", "neurips_winfast.bib")]:
    src = open(f"{SRC}/{path}").read()
    m = re.search(r"doi\s*=\s*[\"{]([^\"}]+)", src)
    pg = re.search(r"pages\s*=\s*[\"{]([^\"}]+)", src)
    d_ok = mine[key][1]["doi"] == m.group(1); p_ok = mine[key][1]["pages"] == pg.group(1)
    ok &= d_ok and p_ok
    print(f"{key:24s} doi_match={d_ok} pages_match={p_ok}")
print("ALL_OK" if ok else "MISMATCH_FOUND")
