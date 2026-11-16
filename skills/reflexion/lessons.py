#!/usr/bin/env python3
"""reflexion: Lektionen aus einer Nachbesprechung in LESSONS.md festhalten.

    python3 lessons.py hinzufuegen --lektion "..." --geplant "..." --passiert "..." --ursache "..." --tags "api,deploy"
    python3 lessons.py liste [--tag api] [--status offen]
    python3 lessons.py aehnlich "Text einer neuen Lektion"

Vor dem Schreiben sucht das Skript nach ähnlichen Lektionen. Ist eine sehr ähnlich, schreibt es
nicht und nennt die Fundstelle. Mit --trotzdem wird dennoch geschrieben.
Nur Standardbibliothek, Python 3.8 oder neuer.
"""

import argparse
import datetime
import difflib
import os
import re
import sys
import unicodedata

STANDARD_DATEI = "LESSONS.md"
GLOBAL_DATEI = os.path.join("~", ".claude", "LESSONS.md")
SCHWELLE_WARNUNG = 0.4
SCHWELLE_STOPP = 0.7
STATUS = ("notiert", "vorgeschlagen", "angewendet")

KOPF = {
    "de": ("# Lessons\n\n"
           "Lektionen aus Nachbesprechungen mit /reflexion. Lies diese Datei, bevor du in diesem Projekt "
           "eine neue Aufgabe beginnst. Jede Lektion nennt eine Datei, einen Befehl, eine Zahl oder eine "
           "Bedingung.\n"),
    "en": ("# Lessons\n\n"
           "Lessons from /reflexion debriefs. Read this file before starting a new task in this project. "
           "Every lesson names a file, a command, a number or a condition.\n"),
}
FELDER = {
    "de": (("geplant", "Geplant"), ("passiert", "Passiert"), ("ursache", "Ursache"), ("fix", "Fix"),
           ("status", "Status"), ("tags", "Tags")),
    "en": (("geplant", "Planned"), ("passiert", "Happened"), ("ursache", "Cause"), ("fix", "Fix"),
           ("status", "Status"), ("tags", "Tags")),
}
STATUS_EN = {"notiert": "logged", "vorgeschlagen": "proposed", "angewendet": "applied"}

STOPPWOERTER = set("""
aber alle als also am an auch auf aus bei beim bin bis bzw da damit dann das dass dem den der des die dies diese
dieser dieses doch dort du durch ein eine einem einen einer eines er es etwa für hat hatte immer in ins ist ja
jede jeden jeder jedes kann kein keine man mehr mit muss nach nicht nie noch nur ob oder ohne schon sein sich sie
sind so soll sollte statt um und uns vom von vor war wenn wer werden wie wird wir wo zu zum zur über
a all also an and are as at be before but by can do does every for from has have if in into is it its never no
not of on only or should so than that the then this to use was when which will with without
""".split())

WORT = re.compile(r"[0-9A-Za-zÄÖÜäöüß_./-]+")
EINTRAG = re.compile(r"^## ", re.M)


class LessonsError(Exception):
    pass


def normalisieren(text):
    text = unicodedata.normalize("NFKC", text).lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return text


def stamm(wort):
    for endung in ("ungen", "ung", "en", "er", "es", "e", "n", "s"):
        if len(wort) > len(endung) + 3 and wort.endswith(endung):
            return wort[:-len(endung)]
    return wort


def kernwoerter(text):
    stopp = set(normalisieren(w) for w in STOPPWOERTER)
    out = []
    for roh in WORT.findall(normalisieren(text)):
        roh = roh.strip("./-")
        teile = [roh] if ("/" in roh or "." in roh) else roh.split("-")
        for w in teile:
            if len(w) < 2 or w in stopp:
                continue
            out.append(w if re.search(r"\d", w) else stamm(w))
    return out


def aehnlichkeit(a, b):
    wa, wb = set(kernwoerter(a)), set(kernwoerter(b))
    if not wa or not wb:
        return 0.0
    jaccard = len(wa & wb) / float(len(wa | wb))
    ueberdeckung = len(wa & wb) / float(min(len(wa), len(wb)))
    folge = difflib.SequenceMatcher(None, " ".join(sorted(wa)), " ".join(sorted(wb))).ratio()
    return round(max(jaccard, 0.6 * ueberdeckung + 0.4 * folge), 3)


def pfad(datei, global_):
    return os.path.expanduser(GLOBAL_DATEI if global_ else datei)


def lesen(path):
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def eintraege(text):
    teile = EINTRAG.split(text)
    out = []
    for teil in teile[1:]:
        block = "## " + teil.rstrip()
        kopf = block.split("\n", 1)[0]
        m = re.match(r"^## (\d{4}-\d{2}-\d{2})\s*[·|-]+\s*(.+)$", kopf)
        felder = {}
        for zeile in block.split("\n")[1:]:
            fm = re.match(r"^- ([^:]+):\s*(.*)$", zeile)
            if fm:
                felder[fm.group(1).strip().lower()] = fm.group(2).strip()
        out.append({
            "datum": m.group(1) if m else "",
            "lektion": m.group(2).strip() if m else kopf[3:].strip(),
            "felder": felder,
            "text": block,
        })
    return out


def tags_von(eintrag):
    roh = eintrag["felder"].get("tags", "")
    return [t.strip().lower() for t in roh.split(",") if t.strip()]


def status_von(eintrag):
    roh = eintrag["felder"].get("status", "").lower()
    for de, en in STATUS_EN.items():
        if roh.startswith(de) or roh.startswith(en):
            return de
    return "notiert"


def aehnliche(text, vorhandene, schwelle=SCHWELLE_WARNUNG):
    treffer = []
    for e in vorhandene:
        wert = aehnlichkeit(text, e["lektion"])
        if wert >= schwelle:
            treffer.append((wert, e))
    treffer.sort(key=lambda t: -t[0])
    return treffer


def eintrag_bauen(lektion, geplant="", passiert="", ursache="", fix="", status="notiert", tags="",
                  sprache="de", datum=None):
    if not lektion or not lektion.strip():
        raise LessonsError("die Lektion ist leer")
    if status not in STATUS:
        raise LessonsError("Status muss einer von %s sein" % ", ".join(STATUS))
    datum = datum or datetime.date.today().isoformat()
    werte = {"geplant": geplant, "passiert": passiert, "ursache": ursache, "fix": fix,
             "status": status if sprache == "de" else STATUS_EN[status],
             "tags": ",".join(t.strip().lower() for t in tags.split(",") if t.strip())}
    zeilen = ["## %s · %s" % (datum, " ".join(lektion.split()))]
    for key, label in FELDER[sprache]:
        if werte[key]:
            zeilen.append("- %s: %s" % (label, " ".join(werte[key].split())))
    return "\n".join(zeilen) + "\n"


def hinzufuegen(path, lektion, trotzdem=False, sprache="de", **felder):
    text = lesen(path)
    vorhandene = eintraege(text)
    treffer = aehnliche(lektion, vorhandene)
    if treffer and treffer[0][0] >= SCHWELLE_STOPP and not trotzdem:
        wert, e = treffer[0]
        raise LessonsError("sehr ähnlich zu einer vorhandenen Lektion (%d %%):\n  %s · %s\n"
                           "Ergänze die vorhandene Lektion oder schreib mit --trotzdem."
                           % (round(wert * 100), e["datum"], e["lektion"]))
    eintrag = eintrag_bauen(lektion, sprache=sprache, **felder)
    if not text.strip():
        text = KOPF[sprache]
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.rstrip("\n") + "\n\n" + eintrag)
    return eintrag, [t for t in treffer if t[0] < SCHWELLE_STOPP or trotzdem]


def filtern(vorhandene, tag=None, status=None):
    out = vorhandene
    if tag:
        out = [e for e in out if tag.lower() in tags_von(e)]
    if status == "offen":
        out = [e for e in out if status_von(e) == "vorgeschlagen"]
    elif status:
        out = [e for e in out if status_von(e) == status]
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Lektionen aus /reflexion in LESSONS.md schreiben und lesen.")
    p.add_argument("--datei", default=STANDARD_DATEI, help="Logbuch (Standard: ./LESSONS.md)")
    p.add_argument("--global", dest="global_", action="store_true", help="~/.claude/LESSONS.md verwenden")
    sub = p.add_subparsers(dest="befehl")

    h = sub.add_parser("hinzufuegen", help="eine Lektion anhängen")
    h.add_argument("--lektion", required=True, help="Frage 4: was wir beibehalten oder ändern")
    h.add_argument("--geplant", default="", help="Frage 1: was geplant war")
    h.add_argument("--passiert", default="", help="Frage 2: was tatsächlich passiert ist")
    h.add_argument("--ursache", default="", help="Frage 3: warum es eine Abweichung gab")
    h.add_argument("--fix", default="", help="Zieldatei und Änderung, falls es einen Fix gibt")
    h.add_argument("--status", default="notiert", choices=STATUS)
    h.add_argument("--tags", default="", help="kommagetrennt")
    h.add_argument("--sprache", default="de", choices=["de", "en"], help="Sprache der Feldnamen")
    h.add_argument("--trotzdem", action="store_true", help="auch bei sehr ähnlicher Lektion schreiben")

    l = sub.add_parser("liste", help="vorhandene Lektionen zeigen")
    l.add_argument("--tag")
    l.add_argument("--status", choices=list(STATUS) + ["offen"])

    a = sub.add_parser("aehnlich", help="ähnliche Lektionen zu einem Text suchen, ohne zu schreiben")
    a.add_argument("text")

    args = p.parse_args(argv)
    path = pfad(args.datei, args.global_)
    try:
        if args.befehl == "hinzufuegen":
            eintrag, hinweise = hinzufuegen(
                path, args.lektion, trotzdem=args.trotzdem, sprache=args.sprache, geplant=args.geplant,
                passiert=args.passiert, ursache=args.ursache, fix=args.fix, status=args.status, tags=args.tags)
            print("Geschrieben in %s:\n\n%s" % (path, eintrag.rstrip()))
            for wert, e in hinweise:
                print("\nÄhnlich (%d %%): %s · %s" % (round(wert * 100), e["datum"], e["lektion"]))
        elif args.befehl == "liste":
            if not os.path.isfile(path):
                print("Noch kein Logbuch unter %s." % path)
                return 0
            gefunden = filtern(eintraege(lesen(path)), args.tag, args.status)
            for e in gefunden:
                print(e["text"] + "\n")
            print("%d Lektion(en) in %s" % (len(gefunden), path))
        elif args.befehl == "aehnlich":
            treffer = aehnliche(args.text, eintraege(lesen(path)))
            if not treffer:
                print("Keine ähnliche Lektion in %s." % path)
            for wert, e in treffer:
                print("%3d %%  %s · %s" % (round(wert * 100), e["datum"], e["lektion"]))
            return 1 if treffer and treffer[0][0] >= SCHWELLE_STOPP else 0
        else:
            p.print_help()
            return 2
        return 0
    except LessonsError as e:
        print("lessons.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
