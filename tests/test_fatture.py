import json
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analisi  # noqa: E402
import leggi_fatture  # noqa: E402


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "demo.sqlite"
    leggi_fatture.carica(ROOT / "dati" / "fatture_xml", db)
    return sqlite3.connect(db), db


@pytest.fixture(scope="module")
def ufficiali(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "es.sqlite"
    return leggi_fatture.carica(ROOT / "esempi_ufficiali", db)


def test_esempi_ufficiali_letti(ufficiali):
    assert ufficiali.execute("SELECT COUNT(*), SUM(valido_xsd) FROM file").fetchone() == (3, 3)
    # FPR03 contiene due fatture nello stesso file
    assert ufficiali.execute("SELECT COUNT(*) FROM documenti").fetchone()[0] == 4
    assert ufficiali.execute("SELECT imponibile_cent, imposta_cent FROM documenti WHERE file LIKE '%FPR01%'").fetchone() == (500, 110)


def test_esempio_ufficiale_righe_diverse_dal_riepilogo(ufficiali):
    # nel file di esempio FPR03 le righe sommano 25,00 ma il riepilogo dice 27,00: lo schema XSD non lo controlla
    r = ufficiali.execute("SELECT dettaglio FROM controlli WHERE controllo = 'Righe diverse dal riepilogo'").fetchall()
    assert r == [("Somma righe 25,00, riepilogo 27,00",)]


def test_tutti_i_problemi_inseriti_trovati(demo):
    con, _ = demo
    problemi = json.loads((ROOT / "dati" / "problemi_inseriti.json").read_text())
    trovati = {(n, c) for n, c in con.execute(
        "SELECT d.numero, c.controllo FROM controlli c JOIN documenti d ON d.id = c.documento_id")}
    attesi = {
        "file_duplicato": "Duplicato", "non_valido_schema": "Non valido (schema)",
        "nota_senza_riferimento": "Nota senza riferimento", "totale_non_quadra": "Totale non quadra",
    }
    for p in problemi:
        if p["tipo"] == "totale_non_quadra" and abs(Decimal(p["differenza"])) <= Decimal("0.01"):
            assert (p["numero"], attesi[p["tipo"]]) not in trovati  # arrotondamento di un centesimo: tollerato
        else:
            assert (p["numero"], attesi[p["tipo"]]) in trovati
    # nessun controllo in più rispetto ai problemi inseriti
    assert len(trovati) == sum(1 for p in problemi if not (p["tipo"] == "totale_non_quadra" and abs(Decimal(p["differenza"])) <= Decimal("0.01")))


def test_riconciliazione(demo):
    con, db = demo
    tutto = con.execute("SELECT SUM(imponibile_cent) FROM documenti").fetchone()[0]
    inclusi = con.execute("SELECT SUM(imponibile_cent) FROM documenti WHERE incluso").fetchone()[0]
    esclusi = con.execute("SELECT SUM(imponibile_cent) FROM documenti WHERE NOT incluso").fetchone()[0]
    assert inclusi + esclusi == tutto
    a = analisi.analizza(db)
    netto = a["totali"]["netto"]
    assert netto == a["totali"]["vendite"] - a["totali"]["note"]
    assert sum(m["netto"] for m in a["mesi"]) == netto
    assert sum(c["netto"] for c in a["clienti"]) == netto
    assert sum(p["netto"] for p in a["prodotti"]) == netto  # nelle fatture demo righe e riepilogo coincidono


def test_partite_iva_demo_non_reali():
    clienti = json.loads((ROOT / "dati" / "clienti_demo.json").read_text())
    for c in clienti:
        if c["paese"] == "IT":
            assert c["piva"][7:10] == "000"  # codice ufficio inesistente
