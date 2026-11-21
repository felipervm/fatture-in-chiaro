# Fatture in chiaro

**[Apri la pagina](https://felipervm.github.io/fatture-in-chiaro/)**

Uno strumento in Python che legge le fatture elettroniche italiane (FatturaPA, XML), le controlla e ne ricava un riepilogo commerciale.

I gestionali italiani producono già le fatture in XML. Questo progetto mostra cosa si può ricavare da quei file: fatturato netto mese per mese, peso dei clienti principali, clienti che non comprano da tempo, prodotti e note di credito. Prima dei numeri, controlla che i file siano corretti.

## Dati

**Tutti i dati delle fatture sono inventati.** `scripts/genera_fatture.py` genera un anno (2025) di fatture di una cantina inventata, con clienti e prodotti inventati.

- La partita IVA del cedente è 01234567890, la stessa usata negli esempi ufficiali.
- Le partite IVA dei clienti italiani usano il codice ufficio `000`, che nelle partite IVA reali non esiste.
- Nelle fatture sono inseriti apposta 10 problemi (elencati in `dati/problemi_inseriti.json`) per verificare i controlli.

Lo strumento legge anche i file di esempio ufficiali FatturaPA in `esempi_ufficiali/` (FPR01, FPR02, FPR03).

## Controlli

| Controllo | Cosa verifica | Effetto |
|---|---|---|
| Schema | Il file rispetta lo schema XSD FatturaPA 1.2.1 | Se no, escluso: lo SdI lo scarterebbe |
| Duplicato | Lo stesso documento è arrivato in due file | Il secondo è escluso |
| Numero ripetuto | Lo stesso numero è usato per documenti diversi nello stesso anno | Da verificare |
| Totale non quadra | Totale dichiarato diverso da imponibile + IVA (oltre 1 centesimo) | Si usano i valori del riepilogo |
| Righe diverse dal riepilogo | La somma delle righe non è uguale all’imponibile del riepilogo | Da verificare |
| Nota senza riferimento | Nota di credito senza fattura collegata, o con una fattura non trovata | Da verificare |

Nel file di esempio ufficiale FPR03 le righe della prima fattura sommano 25,00 euro ma il riepilogo dice 27,00: il file è valido per lo schema, che non controlla i calcoli.

## Come si usa

```bash
pip install -r requirements.txt
python scripts/genera_fatture.py                                  # solo per i dati dimostrativi
python scripts/leggi_fatture.py dati/fatture_xml dati/fatture.sqlite
python scripts/analisi.py dati/fatture.sqlite site/data.json
python scripts/build_site.py                                      # genera docs/index.html
pytest -q
```

`leggi_fatture.py` funziona con qualsiasi cartella di file FatturaPA ordinaria.

## Struttura

```
dati/fatture_xml/   fatture dimostrative (XML)
esempi_ufficiali/   file di esempio FatturaPA
xsd/                schema FatturaPA 1.2.1 e firma digitale
scripts/            generazione, lettura e controlli, analisi, pagina
tests/              test automatici
docs/               pagina pubblicata
```

## Fonti

Schema XSD FatturaPA 1.2.1 (Agenzia delle Entrate) e file di esempio ufficiali, presi dal progetto [php-validatore-fattura-elettronica](https://github.com/Slamdunk/php-validatore-fattura-elettronica) (licenza MIT). Nello schema ho cambiato solo il percorso dello schema della firma digitale, per usare la copia locale senza rete.

Progetto di [Felipe Mattos](https://www.linkedin.com/in/felipervm/), Mondovì. Sviluppato con l’aiuto dell’IA. Progetto indipendente: nessun dato di aziende reali.
