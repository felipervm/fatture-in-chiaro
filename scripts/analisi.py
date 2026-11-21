"""Dal database SQLite al file dati usato dalla pagina.

Uso: python scripts/analisi.py dati/fatture.sqlite site/data.json
"""
import json
import sqlite3
import sys
from datetime import date

FINE = date(2025, 12, 31)
SEGNO = "CASE WHEN tipo = 'TD04' THEN -1 ELSE 1 END"


def tipo_cliente(nome):
    return nome.split(" DEMO")[0].title() if nome and " DEMO" in nome else "Altro"


def analizza(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    q = lambda sql, *a: [dict(r) for r in con.execute(sql, a)]

    tot = q(f"""SELECT SUM({SEGNO} * imponibile_cent) netto, SUM({SEGNO} * imposta_cent) iva,
                SUM(CASE WHEN tipo != 'TD04' THEN imponibile_cent END) vendite,
                SUM(CASE WHEN tipo = 'TD04' THEN imponibile_cent END) note,
                SUM(CASE WHEN tipo != 'TD04' THEN 1 END) fatture, SUM(CASE WHEN tipo = 'TD04' THEN 1 END) n_note,
                COUNT(DISTINCT cliente_piva) clienti,
                SUM(CASE WHEN cliente_paese != 'IT' THEN {SEGNO} * imponibile_cent END) estero
                FROM documenti WHERE incluso""")[0]
    file = q("SELECT COUNT(*) n, SUM(valido_xsd) validi FROM file")[0]
    docs = q("SELECT COUNT(*) n, SUM(incluso) inclusi FROM documenti")[0]

    mesi = q(f"""SELECT substr(data,1,7) mese, SUM({SEGNO} * imponibile_cent) netto,
                 SUM(CASE WHEN tipo='TD04' THEN imponibile_cent ELSE 0 END) note, COUNT(*) documenti
                 FROM documenti WHERE incluso GROUP BY 1 ORDER BY 1""")

    clienti = q(f"""SELECT cliente_piva piva, cliente_paese paese, MAX(cliente) nome, MAX(cliente_comune) comune,
                    SUM({SEGNO} * imponibile_cent) netto, SUM(CASE WHEN tipo!='TD04' THEN 1 ELSE 0 END) fatture,
                    SUM(CASE WHEN tipo='TD04' THEN imponibile_cent ELSE 0 END) note,
                    MIN(data) prima, MAX(CASE WHEN tipo!='TD04' THEN data END) ultima
                    FROM documenti WHERE incluso GROUP BY 1,2 ORDER BY netto DESC""")
    for c in clienti:
        c["tipo"] = tipo_cliente(c["nome"])
        ultima = date.fromisoformat(c["ultima"])
        c["giorni_senza"] = (FINE - ultima).days
        attivi = (ultima - date.fromisoformat(c["prima"])).days
        c["intervallo_medio"] = round(attivi / (c["fatture"] - 1)) if c["fatture"] > 1 else None
        # "da sentire": cliente abituale che non riceve fatture da molto più del suo ritmo normale
        c["da_sentire"] = bool(c["fatture"] >= 3 and c["intervallo_medio"] and c["giorni_senza"] > max(90, 3 * c["intervallo_medio"]))
    totale_clienti = sum(c["netto"] for c in clienti)
    top10 = sum(c["netto"] for c in clienti[:10])

    prodotti = q(f"""SELECT r.codice, MAX(r.descrizione) descrizione,
                     SUM(CASE WHEN d.tipo!='TD04' THEN r.quantita ELSE 0 END) bottiglie,
                     SUM(CASE WHEN d.tipo='TD04' THEN r.quantita ELSE 0 END) bottiglie_rese,
                     SUM(CASE WHEN d.tipo='TD04' THEN -r.totale_cent ELSE r.totale_cent END) netto
                     FROM righe r JOIN documenti d ON d.id = r.documento_id WHERE d.incluso GROUP BY 1 ORDER BY netto DESC""")

    controlli = q("""SELECT c.controllo, c.dettaglio, c.effetto, c.file, d.numero, d.data, d.cliente, d.tipo
                     FROM controlli c LEFT JOIN documenti d ON d.id = c.documento_id ORDER BY c.controllo, d.data""")
    esclusi = q("SELECT SUM(imponibile_cent) imponibile, COUNT(*) n FROM documenti WHERE NOT incluso")[0]
    return {
        "periodo": ["2025-01-01", "2025-12-31"],
        "file": file, "documenti": docs, "totali": tot, "esclusi": esclusi,
        "concentrazione": {"top10": top10 / totale_clienti, "primo": clienti[0]["netto"] / totale_clienti, "clienti": len(clienti)},
        "mesi": mesi, "clienti": clienti, "prodotti": prodotti, "controlli": controlli,
    }


if __name__ == "__main__":
    out = analizza(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    t = out["totali"]
    print("netto", t["netto"] / 100, "note", t["note"] / 100, "top10", round(out["concentrazione"]["top10"], 3),
          "da sentire", sum(c["da_sentire"] for c in out["clienti"]), "controlli", len(out["controlli"]))
