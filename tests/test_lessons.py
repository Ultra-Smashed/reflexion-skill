import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import SKILL, lessons

BATCH = ("Batch-Schreibzugriffe auf höchstens 100 Zeilen begrenzen und die zurückgegebene Zeilenzahl "
         "prüfen, nicht den Statuscode.")
DUBLETTE = "Schreibzugriffe im Batch auf 100 Zeilen begrenzen und die Zeilenzahl prüfen statt des Statuscodes."
ANDERE = [
    "Zeitstempel immer in UTC speichern und vergleichen, nie in Ortszeit.",
    "Nach jedem Deploy die laufende Version jedes Dienstes prüfen, nicht nur den Exit-Code.",
    "Retry-Schleifen mit exponentiellem Backoff bauen und auf 5 Versuche begrenzen.",
    "Supabase-Migrationen mit date +%Y%m%d%H%M%S benennen.",
]


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.datei = os.path.join(self.tmp, "LESSONS.md")

    def text(self):
        with open(self.datei, encoding="utf-8") as fh:
            return fh.read()


class Aehnlichkeit(unittest.TestCase):
    def test_umformulierung_ist_dublette(self):
        self.assertGreaterEqual(lessons.aehnlichkeit(BATCH, DUBLETTE), lessons.SCHWELLE_STOPP)

    def test_lockere_umformulierung_warnt(self):
        wert = lessons.aehnlichkeit(BATCH, "Bei Batch-Uploads die Zeilenzahl prüfen statt dem Statuscode, Limit 100 Zeilen")
        self.assertGreaterEqual(wert, lessons.SCHWELLE_WARNUNG)

    def test_fremde_lektionen_bleiben_unter_der_warnschwelle(self):
        for text in ANDERE:
            self.assertLess(lessons.aehnlichkeit(BATCH, text), lessons.SCHWELLE_WARNUNG, text)
        for a in ANDERE:
            for b in ANDERE:
                if a != b:
                    self.assertLess(lessons.aehnlichkeit(a, b), lessons.SCHWELLE_WARNUNG, (a, b))

    def test_englisch(self):
        a = "Cap batch writes at 100 rows and check the returned row count, not the status code."
        b = "Batch writes over 100 rows fail silently; limit to 100 and verify row count instead of status code."
        self.assertGreaterEqual(lessons.aehnlichkeit(a, b), lessons.SCHWELLE_WARNUNG)

    def test_leer(self):
        self.assertEqual(lessons.aehnlichkeit("", BATCH), 0.0)
        self.assertEqual(lessons.aehnlichkeit("und die der", BATCH), 0.0)

    def test_symmetrisch(self):
        self.assertEqual(lessons.aehnlichkeit(BATCH, DUBLETTE), lessons.aehnlichkeit(DUBLETTE, BATCH))

    def test_kernwoerter(self):
        w = lessons.kernwoerter("Die Batch-Uploads in CLAUDE.md prüfen")
        self.assertIn("batch", w)
        self.assertIn("claude.md", w)
        self.assertNotIn("die", w)


class Eintrag(unittest.TestCase):
    def test_format(self):
        e = lessons.eintrag_bauen("Lektion  mit\nUmbruch.", geplant="A", passiert="B", ursache="C",
                                  fix="CLAUDE.md", status="angewendet", tags="API, Deploy", datum="2026-11-16")
        self.assertEqual(e, "## 2026-11-16 · Lektion mit Umbruch.\n- Geplant: A\n- Passiert: B\n- Ursache: C\n"
                            "- Fix: CLAUDE.md\n- Status: angewendet\n- Tags: api,deploy\n")

    def test_englische_feldnamen(self):
        e = lessons.eintrag_bauen("Lesson.", geplant="A", status="vorgeschlagen", sprache="en", datum="2026-11-16")
        self.assertIn("- Planned: A", e)
        self.assertIn("- Status: proposed", e)

    def test_leere_lektion(self):
        with self.assertRaises(lessons.LessonsError):
            lessons.eintrag_bauen("  ")

    def test_falscher_status(self):
        with self.assertRaises(lessons.LessonsError):
            lessons.eintrag_bauen("x", status="fertig")


class Hinzufuegen(Tmp):
    def test_neue_datei_mit_kopf(self):
        lessons.hinzufuegen(self.datei, BATCH, tags="api")
        text = self.text()
        self.assertTrue(text.startswith("# Lessons\n"))
        self.assertIn("· " + BATCH, text)

    def test_anhaengen(self):
        lessons.hinzufuegen(self.datei, BATCH)
        lessons.hinzufuegen(self.datei, ANDERE[0])
        self.assertEqual(len(lessons.eintraege(self.text())), 2)
        self.assertEqual(self.text().count("# Lessons"), 1)

    def test_dublette_wird_abgelehnt(self):
        lessons.hinzufuegen(self.datei, BATCH)
        with self.assertRaises(lessons.LessonsError) as ctx:
            lessons.hinzufuegen(self.datei, DUBLETTE)
        self.assertIn("ähnlich", str(ctx.exception))
        self.assertEqual(len(lessons.eintraege(self.text())), 1)

    def test_dublette_mit_trotzdem(self):
        lessons.hinzufuegen(self.datei, BATCH)
        _, hinweise = lessons.hinzufuegen(self.datei, DUBLETTE, trotzdem=True)
        self.assertEqual(len(lessons.eintraege(self.text())), 2)
        self.assertTrue(hinweise)

    def test_warnung_ohne_stopp(self):
        lessons.hinzufuegen(self.datei, BATCH)
        _, hinweise = lessons.hinzufuegen(self.datei, "Bei Batch-Uploads die Zeilenzahl prüfen statt dem Statuscode, Limit 100 Zeilen")
        self.assertEqual(len(hinweise), 1)

    def test_vorhandene_datei_von_hand(self):
        with open(self.datei, "w", encoding="utf-8") as fh:
            fh.write("# Meine Lektionen\n\nFreitext.\n\n## 2026-01-02 · Alte Lektion zu Backups.\n- Tags: backup\n")
        lessons.hinzufuegen(self.datei, ANDERE[0])
        text = self.text()
        self.assertTrue(text.startswith("# Meine Lektionen"))
        self.assertEqual([e["datum"] for e in lessons.eintraege(text)][0], "2026-01-02")


class Liste(Tmp):
    def setUp(self):
        Tmp.setUp(self)
        lessons.hinzufuegen(self.datei, BATCH, tags="api,upload")
        lessons.hinzufuegen(self.datei, ANDERE[0], tags="zeit", status="vorgeschlagen", fix="CLAUDE.md")
        lessons.hinzufuegen(self.datei, ANDERE[1], tags="deploy", status="angewendet")

    def test_filter(self):
        alle = lessons.eintraege(self.text())
        self.assertEqual(len(lessons.filtern(alle, tag="API")), 1)
        self.assertEqual(len(lessons.filtern(alle, tag="ap")), 0)
        self.assertEqual([e["lektion"] for e in lessons.filtern(alle, status="offen")], [ANDERE[0]])
        self.assertEqual(len(lessons.filtern(alle, status="angewendet")), 1)
        self.assertEqual(len(lessons.filtern(alle, status="notiert")), 1)

    def test_englischer_status(self):
        lessons.hinzufuegen(self.datei, ANDERE[2], status="vorgeschlagen", sprache="en")
        offen = lessons.filtern(lessons.eintraege(self.text()), status="offen")
        self.assertEqual(len(offen), 2)


class Cli(Tmp):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lessons.main(["--datei", self.datei] + list(args))
        return code, out.getvalue(), err.getvalue()

    def test_ablauf(self):
        code, out, _ = self.run_cli("hinzufuegen", "--lektion", BATCH, "--geplant", "500 Zeilen", "--tags", "api")
        self.assertEqual(code, 0)
        self.assertIn("Geschrieben", out)
        code, out, _ = self.run_cli("aehnlich", DUBLETTE)
        self.assertEqual(code, 1)
        self.assertIn("%", out)
        code, _, err = self.run_cli("hinzufuegen", "--lektion", DUBLETTE)
        self.assertEqual(code, 1)
        self.assertIn("--trotzdem", err)
        code, out, _ = self.run_cli("liste", "--tag", "api")
        self.assertIn("1 Lektion(en)", out)
        code, out, _ = self.run_cli("aehnlich", ANDERE[0])
        self.assertEqual(code, 0)
        self.assertIn("Keine ähnliche", out)

    def test_liste_ohne_datei(self):
        code, out, _ = self.run_cli("liste")
        self.assertEqual(code, 0)
        self.assertIn("Noch kein Logbuch", out)

    def test_global(self):
        home = os.path.join(self.tmp, "home")
        alt = os.environ.get("HOME")
        os.environ["HOME"] = home
        try:
            with redirect_stdout(io.StringIO()):
                lessons.main(["--global", "hinzufuegen", "--lektion", BATCH])
        finally:
            if alt is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = alt
        self.assertTrue(os.path.isfile(os.path.join(home, ".claude", "LESSONS.md")))

    def test_als_skript(self):
        p = subprocess.run([sys.executable, os.path.join(SKILL, "lessons.py"), "--help"], stdout=subprocess.PIPE)
        self.assertEqual(p.returncode, 0)
        self.assertIn(b"aehnlich", p.stdout)


if __name__ == "__main__":
    unittest.main()
