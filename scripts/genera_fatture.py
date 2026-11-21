"""Genera le fatture di dimostrazione (FatturaPA FPR12) di un'azienda inventata.

Nessun dato reale: azienda, clienti, prodotti e partite IVA sono inventati.
Le partite IVA usano il codice ufficio "000", che nelle partite IVA reali non esiste,
così non possono coincidere con un'impresa vera. Il cedente usa 01234567890,
lo stesso numero di esempio usato dall'Agenzia delle Entrate nei suoi file di prova.

Alcuni problemi vengono inseriti apposta (e sono elencati in dati/problemi_inseriti.json)
per verificare che i controlli li trovino.

Uso: python scripts/genera_fatture.py
"""
import json
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dati" / "fatture_xml"
SEED = 2025
ANNO = 2025
C = Decimal("0.01")

CEDENTE = {"piva": "01234567890", "nome": "CANTINA DIMOSTRATIVA SRL", "via": "Via Esempio 1", "cap": "12084", "comune": "Mondovì", "prov": "CN"}

PRODOTTI = [  # codice, descrizione, prezzo per bottiglia (euro)
    ("DOL75", "Dolcetto di Dogliani DOCG 0,75 l", "7.80"),
    ("DOL150", "Dolcetto di Dogliani DOCG magnum 1,5 l", "18.50"),
    ("BAR75", "Barolo DOCG 0,75 l", "24.00"),
    ("BAR75R", "Barolo DOCG Riserva 0,75 l", "38.00"),
    ("NEB75", "Langhe Nebbiolo DOC 0,75 l", "11.50"),
    ("BAR75B", "Barbera d'Alba DOC 0,75 l", "8.90"),
    ("ARN75", "Roero Arneis DOCG 0,75 l", "9.40"),
    ("MOS75", "Moscato d'Asti DOCG 0,75 l", "8.20"),
    ("ROS75", "Langhe Rosato DOC 0,75 l", "7.20"),
    ("SPU75", "Alta Langa DOCG metodo classico 0,75 l", "19.00"),
]
TIPI = [("Enoteca", 18), ("Ristorante", 22), ("Distributore", 6), ("Hotel", 6), ("Gastronomia", 8)]
PROVINCE = [("CN", "Mondovì"), ("CN", "Cuneo"), ("CN", "Alba"), ("CN", "Bra"), ("TO", "Torino"), ("AT", "Asti"), ("SV", "Savona"), ("GE", "Genova"), ("MI", "Milano")]
ESTERI = [("DE", "Monaco di Baviera", "Distributore"), ("DE", "Amburgo", "Enoteca"), ("NL", "Amsterdam", "Distributore"), ("BE", "Bruxelles", "Enoteca")]
STAGIONE = {1: .55, 2: .6, 3: .8, 4: .95, 5: 1.0, 6: 1.05, 7: 1.1, 8: .7, 9: 1.0, 10: 1.1, 11: 1.35, 12: 1.75}


def piva_finta(n):
    """7 cifre + ufficio 000 + cifra di controllo (algoritmo Luhn usato per le partite IVA)."""
    base = f"{n:07d}000"
    s = 0
    for i, ch in enumerate(base):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return base + str((10 - s % 10) % 10)


def q(x):
    return Decimal(x).quantize(C, rounding=ROUND_HALF_UP)


def clienti(rng):
    out, n = [], 1
    for tipo, quanti in TIPI:
        for _ in range(quanti):
            prov, comune = rng.choice(PROVINCE)
            out.append({"id": f"C{n:03d}", "nome": f"{tipo.upper()} DEMO {n:03d}", "tipo": tipo, "paese": "IT",
                        "piva": piva_finta(1000 + n), "comune": comune, "prov": prov,
                        "peso": rng.lognormvariate(0, 0.8) * (2 if tipo == "Distributore" else 1)})
            n += 1
    for paese, comune, tipo in ESTERI:
        out.append({"id": f"C{n:03d}", "nome": f"{tipo.upper()} DEMO {n:03d}", "tipo": tipo, "paese": paese,
                    "piva": f"{rng.randint(10**8, 10**9 - 1)}00", "comune": comune, "prov": None,
                    "peso": rng.lognormvariate(0, 0.8) * 3})
        n += 1
    # una parte dei clienti smette di comprare a metà anno: serve per la lettura "ultimo acquisto"
    for c in rng.sample(out, 7):
        c["fine"] = date(ANNO, rng.randint(4, 8), rng.randint(1, 28))
    return out


def sub(parent, tag, text=None):
    from lxml import etree
    e = etree.SubElement(parent, tag)
    if text is not None:
        e.text = str(text)
    return e


def fattura_xml(doc, cliente, progressivo):
    from lxml import etree
    NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
    root = etree.Element(f"{{{NS}}}FatturaElettronica", nsmap={"p": NS}, versione="FPR12")
    h = sub(root, "FatturaElettronicaHeader")
    dt = sub(h, "DatiTrasmissione")
    it = sub(dt, "IdTrasmittente"); sub(it, "IdPaese", "IT"); sub(it, "IdCodice", CEDENTE["piva"])
    sub(dt, "ProgressivoInvio", f"{progressivo:05d}")
    sub(dt, "FormatoTrasmissione", "FPR12")
    sub(dt, "CodiceDestinatario", "0000000" if cliente["paese"] == "IT" else "XXXXXXX")
    ced = sub(h, "CedentePrestatore")
    da = sub(ced, "DatiAnagrafici")
    iv = sub(da, "IdFiscaleIVA"); sub(iv, "IdPaese", "IT"); sub(iv, "IdCodice", CEDENTE["piva"])
    an = sub(da, "Anagrafica"); sub(an, "Denominazione", CEDENTE["nome"])
    sub(da, "RegimeFiscale", "RF01")
    se = sub(ced, "Sede"); sub(se, "Indirizzo", CEDENTE["via"]); sub(se, "CAP", CEDENTE["cap"]); sub(se, "Comune", CEDENTE["comune"]); sub(se, "Provincia", CEDENTE["prov"]); sub(se, "Nazione", "IT")
    ces = sub(h, "CessionarioCommittente")
    da = sub(ces, "DatiAnagrafici")
    iv = sub(da, "IdFiscaleIVA"); sub(iv, "IdPaese", cliente["paese"]); sub(iv, "IdCodice", cliente["piva"])
    an = sub(da, "Anagrafica"); sub(an, "Denominazione", cliente["nome"])
    se = sub(ces, "Sede"); sub(se, "Indirizzo", "Via Inventata 10"); sub(se, "CAP", "12100" if cliente["paese"] == "IT" else "00000"); sub(se, "Comune", cliente["comune"])
    if cliente["prov"]:
        sub(se, "Provincia", cliente["prov"])
    sub(se, "Nazione", cliente["paese"])
    b = sub(root, "FatturaElettronicaBody")
    dg = sub(b, "DatiGenerali")
    dgd = sub(dg, "DatiGeneraliDocumento")
    sub(dgd, "TipoDocumento", doc["tipo"]); sub(dgd, "Divisa", "EUR"); sub(dgd, "Data", doc["data"].isoformat()); sub(dgd, "Numero", doc["numero"])
    sub(dgd, "ImportoTotaleDocumento", doc["totale_dichiarato"])
    if doc.get("collegata"):
        fc = sub(dg, "DatiFattureCollegate"); sub(fc, "IdDocumento", doc["collegata"][0]); sub(fc, "Data", doc["collegata"][1].isoformat())
    if doc.get("ddt"):
        for numero, data_ddt in doc["ddt"]:
            d = sub(dg, "DatiDDT"); sub(d, "NumeroDDT", numero); sub(d, "DataDDT", data_ddt.isoformat())
    dbs = sub(b, "DatiBeniServizi")
    for i, r in enumerate(doc["righe"], 1):
        dl = sub(dbs, "DettaglioLinee")
        sub(dl, "NumeroLinea", i)
        ca = sub(dl, "CodiceArticolo"); sub(ca, "CodiceTipo", "INTERNO"); sub(ca, "CodiceValore", r["codice"])
        sub(dl, "Descrizione", r["descrizione"]); sub(dl, "Quantita", f"{r['qta']}.00"); sub(dl, "UnitaMisura", "BT")
        sub(dl, "PrezzoUnitario", r["prezzo"])
        if r["sconto"]:
            sm = sub(dl, "ScontoMaggiorazione"); sub(sm, "Tipo", "SC"); sub(sm, "Percentuale", f"{r['sconto']}.00")
        sub(dl, "PrezzoTotale", r["totale"]); sub(dl, "AliquotaIVA", "22.00" if doc["natura"] is None else "0.00")
        if doc["natura"]:
            sub(dl, "Natura", doc["natura"])
    rie = sub(dbs, "DatiRiepilogo")
    sub(rie, "AliquotaIVA", "22.00" if doc["natura"] is None else "0.00")
    if doc["natura"]:
        sub(rie, "Natura", doc["natura"])
    sub(rie, "ImponibileImporto", doc["imponibile"]); sub(rie, "Imposta", doc["imposta"])
    if doc["natura"] is None:
        sub(rie, "EsigibilitaIVA", "I")
    else:
        sub(rie, "RiferimentoNormativo", "Non imponibile art. 41 DL 331/93")
    dp = sub(b, "DatiPagamento"); sub(dp, "CondizioniPagamento", "TP02")
    dd = sub(dp, "DettaglioPagamento"); sub(dd, "ModalitaPagamento", "MP05")
    sub(dd, "DataScadenzaPagamento", (doc["data"] + timedelta(days=60)).isoformat()); sub(dd, "ImportoPagamento", doc["totale"])
    if doc.get("rompi_schema"):
        dgd.remove(dgd.find("Divisa"))  # Divisa è obbligatoria: il file non è valido
    return root


def riga(rng, prodotto, qta, sconto):
    codice, descr, prezzo = prodotto
    tot = q(Decimal(prezzo) * qta * (Decimal(100 - sconto) / 100))
    return {"codice": codice, "descrizione": descr, "qta": qta, "prezzo": prezzo, "sconto": sconto, "totale": tot}


def documento(rng, numero, data, cliente, righe, tipo="TD01", **extra):
    imponibile = sum((r["totale"] for r in righe), Decimal("0"))
    natura = "N3.2" if cliente["paese"] != "IT" else None
    imposta = q(imponibile * Decimal("0.22")) if natura is None else Decimal("0.00")
    totale = imponibile + imposta
    return {"tipo": tipo, "numero": numero, "data": data, "cliente": cliente["id"], "righe": righe, "natura": natura,
            "imponibile": imponibile, "imposta": imposta, "totale": totale, "totale_dichiarato": totale, **extra}


def main():
    from lxml import etree
    rng = random.Random(SEED)
    cli = clienti(rng)
    pesi = [c["peso"] for c in cli]
    docs, n = [], 0
    giorno = date(ANNO, 1, 2)
    while giorno <= date(ANNO, 12, 30):
        if giorno.weekday() < 5:
            for _ in range(rng.choices([0, 1, 2, 3, 4, 5, 6], weights=[1, 3, 4, 4, 3, 2, 1])[0]):
                if rng.random() > STAGIONE[giorno.month] / 1.75:
                    continue
                c = rng.choices(cli, weights=pesi)[0]
                if c.get("fine") and giorno > c["fine"]:
                    continue
                k = rng.randint(1, 4) + (2 if c["tipo"] == "Distributore" else 0)
                righe = []
                for p in rng.sample(PRODOTTI, min(k, len(PRODOTTI))):
                    qta = rng.choice([6, 12, 18, 24, 36]) * (3 if c["tipo"] == "Distributore" else 1)
                    sconto = rng.choice([0, 0, 0, 5, 10]) if c["tipo"] in ("Distributore", "Hotel") else 0
                    righe.append(riga(rng, p, qta, sconto))
                n += 1
                extra = {}
                if c["tipo"] == "Distributore" and rng.random() < .5:
                    extra = {"tipo": "TD24", "ddt": [(f"DDT{n:04d}", giorno - timedelta(days=rng.randint(3, 20)))]}
                    extra["ddt"][0] = (extra["ddt"][0][0], max(extra["ddt"][0][1], date(ANNO, 1, 1)))
                docs.append(documento(rng, f"{n}/{ANNO}", giorno, c, righe, **extra))
        giorno += timedelta(days=1)

    # note di credito (TD04) su circa il 4% delle fatture: resi o rotture
    for d in rng.sample([d for d in docs if d["data"] < date(ANNO, 12, 1)], round(len(docs) * .04)):
        c = next(x for x in cli if x["id"] == d["cliente"])
        r0 = rng.choice(d["righe"])
        qta = max(6, min(r0["qta"], rng.choice([6, 12])))
        righe = [riga(rng, (r0["codice"], r0["descrizione"], r0["prezzo"]), qta, r0["sconto"])]
        n += 1
        docs.append(documento(rng, f"{n}/{ANNO}", d["data"] + timedelta(days=rng.randint(5, 40)), c, righe, tipo="TD04",
                              collegata=(d["numero"], d["data"])))

    docs = [d for d in docs if d["data"].year == ANNO]
    docs.sort(key=lambda d: (d["data"], int(d["numero"].split("/")[0])))

    # problemi inseriti apposta per verificare i controlli
    problemi = []
    for d in rng.sample([d for d in docs if d["tipo"] in ("TD01", "TD24")], 4):
        delta = rng.choice([Decimal("0.01"), Decimal("10.00"), Decimal("-0.02"), Decimal("120.00")])
        d["totale_dichiarato"] = d["totale"] + delta
        problemi.append({"tipo": "totale_non_quadra", "numero": d["numero"], "differenza": str(delta)})
    for d in rng.sample([d for d in docs if d["tipo"] == "TD04"], 2):
        d.pop("collegata", None)
        problemi.append({"tipo": "nota_senza_riferimento", "numero": d["numero"]})
    rotto = rng.choice([d for d in docs if d["tipo"] == "TD01"])
    rotto["rompi_schema"] = True
    problemi.append({"tipo": "non_valido_schema", "numero": rotto["numero"]})
    duplicati = rng.sample([d for d in docs if d["tipo"] == "TD01"], 3)
    for d in duplicati:
        problemi.append({"tipo": "file_duplicato", "numero": d["numero"]})

    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.xml"):
        f.unlink()
    prog = 0
    clienti_by = {c["id"]: c for c in cli}
    for d in docs + duplicati:
        prog += 1
        root = fattura_xml(d, clienti_by[d["cliente"]], prog)
        nome = f"IT{CEDENTE['piva']}_{prog:05d}.xml"
        etree.ElementTree(root).write(str(OUT / nome), xml_declaration=True, encoding="UTF-8", pretty_print=True)
    (ROOT / "dati" / "problemi_inseriti.json").write_text(json.dumps(problemi, indent=1, ensure_ascii=False))
    (ROOT / "dati" / "clienti_demo.json").write_text(json.dumps(
        [{k: (str(v) if isinstance(v, date) else v) for k, v in c.items() if k != "peso"} for c in cli], indent=1, ensure_ascii=False))
    print(f"{prog} file XML, {len(docs)} documenti, {len(cli)} clienti, {len(problemi)} problemi inseriti")


if __name__ == "__main__":
    main()
