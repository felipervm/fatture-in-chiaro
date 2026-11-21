"""Legge una cartella di fatture elettroniche (FatturaPA, XML), le controlla e le carica in SQLite.

Uso: python scripts/leggi_fatture.py dati/fatture_xml dati/fatture.sqlite

Funziona con qualsiasi file FatturaPA ordinaria (FPR12/FPA12): è testato anche
sui file di esempio ufficiali in esempi_ufficiali/.
"""
import sqlite3
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
XSD = ROOT / "xsd" / "Schema_VFPR121a.xsd"
TOLLERANZA = Decimal("0.01")

SCHEMA_SQL = """
CREATE TABLE file (nome TEXT PRIMARY KEY, valido_xsd INTEGER, errore_xsd TEXT);
CREATE TABLE documenti (
  id INTEGER PRIMARY KEY, file TEXT, corpo INTEGER, tipo TEXT, numero TEXT, data TEXT,
  cedente_piva TEXT, cedente TEXT, cliente_paese TEXT, cliente_piva TEXT, cliente TEXT, cliente_comune TEXT,
  imponibile_cent INTEGER, imposta_cent INTEGER, totale_dichiarato_cent INTEGER,
  somma_righe_cent INTEGER, collegata_numero TEXT, collegata_data TEXT, natura TEXT,
  incluso INTEGER, motivo_esclusione TEXT);
CREATE TABLE righe (documento_id INTEGER, linea INTEGER, codice TEXT, descrizione TEXT,
  quantita REAL, prezzo_unitario_cent INTEGER, sconto_pct REAL, totale_cent INTEGER);
CREATE TABLE controlli (documento_id INTEGER, file TEXT, controllo TEXT, dettaglio TEXT, effetto TEXT);
"""


def cent(x):
    return int((Decimal(x) * 100).quantize(Decimal("1"))) if x not in (None, "") else None


def t(node, path):
    e = node.find(path)
    return e.text.strip() if e is not None and e.text else None


def denominazione(node):
    if node is None:
        return None
    nome = t(node, "DatiAnagrafici/Anagrafica/Denominazione")
    if nome:
        return nome
    return " ".join(x for x in (t(node, "DatiAnagrafici/Anagrafica/Nome"), t(node, "DatiAnagrafici/Anagrafica/Cognome")) if x)


def euro(c):
    return f"{c / 100:+,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if c is not None else ""


def euro_s(c):
    return euro(c).lstrip("+")


def leggi_file(path, schema):
    doc = etree.parse(str(path), etree.XMLParser(no_network=True, resolve_entities=False))
    valido = schema.validate(doc)
    errore = None if valido else str(schema.error_log.last_error)
    root = doc.getroot()
    header = root.find("FatturaElettronicaHeader")
    ced, ces = header.find("CedentePrestatore"), header.find("CessionarioCommittente")
    out = []
    for i, body in enumerate(root.findall("FatturaElettronicaBody"), 1):
        g = body.find("DatiGenerali/DatiGeneraliDocumento")
        righe = []
        for r in body.findall("DatiBeniServizi/DettaglioLinee"):
            sconto = t(r, "ScontoMaggiorazione/Percentuale")
            righe.append({
                "linea": int(t(r, "NumeroLinea")),
                "codice": t(r, "CodiceArticolo/CodiceValore"),
                "descrizione": t(r, "Descrizione"),
                "quantita": float(t(r, "Quantita") or 1),
                "prezzo": cent(t(r, "PrezzoUnitario")),
                "sconto": float(sconto) if sconto else 0.0,
                "totale": cent(t(r, "PrezzoTotale")),
            })
        rie = body.findall("DatiBeniServizi/DatiRiepilogo")
        nature = sorted({t(x, "Natura") for x in rie if t(x, "Natura")})
        out.append({
            "corpo": i, "tipo": t(g, "TipoDocumento"), "numero": t(g, "Numero"), "data": t(g, "Data"),
            "cedente_piva": (t(ced, "DatiAnagrafici/IdFiscaleIVA/IdPaese") or "") + (t(ced, "DatiAnagrafici/IdFiscaleIVA/IdCodice") or ""),
            "cedente": denominazione(ced),
            "cliente_paese": t(ces, "DatiAnagrafici/IdFiscaleIVA/IdPaese") or t(ces, "Sede/Nazione"),
            "cliente_piva": t(ces, "DatiAnagrafici/IdFiscaleIVA/IdCodice") or t(ces, "DatiAnagrafici/CodiceFiscale"),
            "cliente": denominazione(ces), "cliente_comune": t(ces, "Sede/Comune"),
            "imponibile": sum(cent(t(x, "ImponibileImporto")) or 0 for x in rie),
            "imposta": sum(cent(t(x, "Imposta")) or 0 for x in rie),
            "totale_dichiarato": cent(t(g, "ImportoTotaleDocumento")),
            "somma_righe": sum(r["totale"] or 0 for r in righe),
            "collegata_numero": t(body, "DatiGenerali/DatiFattureCollegate/IdDocumento"),
            "collegata_data": t(body, "DatiGenerali/DatiFattureCollegate/Data"),
            "natura": ",".join(nature) or None,
            "righe": righe,
        })
    return valido, errore, out


def carica(cartella, db_path):
    schema = etree.XMLSchema(etree.parse(str(XSD), etree.XMLParser(no_network=True)))
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA_SQL)
    visti = {}
    numerazione = defaultdict(list)
    controlli = []
    docs = []
    for path in sorted(Path(cartella).glob("*.xml")):
        valido, errore, corpi = leggi_file(path, schema)
        con.execute("INSERT INTO file VALUES (?,?,?)", (path.name, int(valido), errore))
        for d in corpi:
            d["file"] = path.name
            d["incluso"], d["motivo"] = 1, None
            if not valido:
                d["incluso"], d["motivo"] = 0, "Non valido rispetto allo schema: lo SdI lo scarterebbe"
            # stesso documento inviato due volte: stessi cedente, tipo, numero, data, cliente e importi
            chiave = (d["cedente_piva"], d["tipo"], d["numero"], d["data"], d["cliente_piva"], d["imponibile"], d["imposta"])
            if chiave in visti:
                d["incluso"], d["motivo"] = 0, f"Duplicato di {visti[chiave]}"
            elif d["incluso"]:
                visti[chiave] = path.name
                numero_anno = (d["cedente_piva"], d["numero"], (d["data"] or "")[:4])
                numerazione[numero_anno].append(path.name)
            docs.append(d)

    numeri = {(d["cedente_piva"], d["numero"], d["data"]) for d in docs if d["tipo"] != "TD04"}
    for d in docs:
        cur = con.execute(
            "INSERT INTO documenti (file,corpo,tipo,numero,data,cedente_piva,cedente,cliente_paese,cliente_piva,cliente,cliente_comune,"
            "imponibile_cent,imposta_cent,totale_dichiarato_cent,somma_righe_cent,collegata_numero,collegata_data,natura,incluso,motivo_esclusione)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (d["file"], d["corpo"], d["tipo"], d["numero"], d["data"], d["cedente_piva"], d["cedente"], d["cliente_paese"],
             d["cliente_piva"], d["cliente"], d["cliente_comune"], d["imponibile"], d["imposta"], d["totale_dichiarato"],
             d["somma_righe"], d["collegata_numero"], d["collegata_data"], d["natura"], d["incluso"], d["motivo"]))
        did = cur.lastrowid
        con.executemany("INSERT INTO righe VALUES (?,?,?,?,?,?,?,?)",
                        [(did, r["linea"], r["codice"], r["descrizione"], r["quantita"], r["prezzo"], r["sconto"], r["totale"]) for r in d["righe"]])
        if d["motivo"]:
            tipo = "Duplicato" if d["motivo"].startswith("Duplicato") else "Non valido (schema)"
            controlli.append((did, d["file"], tipo, d["motivo"], "Escluso dai totali"))
        if d["totale_dichiarato"] is not None:
            diff = d["totale_dichiarato"] - (d["imponibile"] + d["imposta"])
            if abs(diff) > int(TOLLERANZA * 100):
                controlli.append((did, d["file"], "Totale non quadra",
                                  f"Il totale dichiarato è diverso da imponibile + IVA: differenza {euro(diff)} euro",
                                  "Incluso con imponibile e IVA del riepilogo"))
        if d["somma_righe"] != d["imponibile"]:
            controlli.append((did, d["file"], "Righe diverse dal riepilogo",
                              f"Somma righe {euro_s(d['somma_righe'])}, riepilogo {euro_s(d['imponibile'])}", "Da verificare"))
        altri = [f for f in numerazione[(d["cedente_piva"], d["numero"], (d["data"] or "")[:4])] if f != d["file"]]
        if d["incluso"] and altri:
            controlli.append((did, d["file"], "Numero ripetuto",
                              f"Il numero {d['numero']} compare anche in {', '.join(altri)} con contenuto diverso", "Incluso, da verificare"))
        if d["tipo"] == "TD04":
            if not d["collegata_numero"]:
                controlli.append((did, d["file"], "Nota senza riferimento", "Nota di credito senza fattura collegata", "Incluso, da verificare"))
            elif (d["cedente_piva"], d["collegata_numero"], d["collegata_data"]) not in numeri:
                controlli.append((did, d["file"], "Riferimento non trovato",
                                  f"La fattura {d['collegata_numero']} del {d['collegata_data']} non è tra i file letti", "Incluso, da verificare"))
    con.executemany("INSERT INTO controlli VALUES (?,?,?,?,?)", controlli)
    con.commit()
    return con


if __name__ == "__main__":
    con = carica(sys.argv[1], sys.argv[2])
    print(con.execute("SELECT COUNT(*), SUM(valido_xsd) FROM file").fetchone(), "file (totali, validi)")
    print(con.execute("SELECT COUNT(*), SUM(incluso) FROM documenti").fetchone(), "documenti (totali, inclusi)")
    for row in con.execute("SELECT controllo, COUNT(*) FROM controlli GROUP BY 1"):
        print(row)
