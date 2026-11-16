import ast
import json
import os
import re
import unittest

from _load import ROOT, SKILL


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def text_dateien():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in files:
            if f.endswith((".md", ".py", ".json")) or f == "LICENSE":
                yield os.path.join(base, f)


class Repo(unittest.TestCase):
    def test_layout(self):
        for rel in ("README.md", "LICENSE", ".gitignore", ".claude-plugin/plugin.json",
                    ".claude-plugin/marketplace.json", "skills/reflexion/SKILL.md", "skills/reflexion/lessons.py"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)
        self.assertEqual(os.listdir(os.path.join(ROOT, "skills")), ["reflexion"])

    def test_frontmatter(self):
        m = re.match(r"^---\nname: (.+)\ndescription: (.+)\n---\n", read(SKILL, "SKILL.md"))
        self.assertTrue(m)
        self.assertEqual(m.group(1), "reflexion")
        self.assertLess(len(m.group(2)), 1024)
        for phrase in ("/reflexion", "After Action Review", "LESSONS.md", "Nachbesprechung", "fix it"):
            self.assertIn(phrase, m.group(2))

    def test_vier_fragen(self):
        text = read(SKILL, "SKILL.md")
        for frage in ("Was war geplant?", "Was ist tatsächlich passiert?", "Warum weicht das eine vom anderen ab?",
                      "Was behalten wir bei, und was machen wir anders?"):
            self.assertGreaterEqual(text.count(frage), 2, frage)

    def test_befehle_dokumentiert(self):
        for rel in ("README.md", "skills/reflexion/SKILL.md"):
            text = read(ROOT, rel)
            for befehl in ("lessons.py aehnlich", "lessons.py hinzufuegen", "lessons.py liste"):
                self.assertIn(befehl, text, "%s fehlt in %s" % (befehl, rel))

    def test_kein_gedankenstrich_in_doku(self):
        for rel in ("README.md", "skills/reflexion/SKILL.md"):
            text = read(ROOT, rel)
            self.assertNotIn("\u2014", text, rel)
            self.assertNotIn(" \u2013 ", text, rel)

    def test_readme(self):
        text = read(ROOT, "README.md")
        self.assertIn("github.com/Ultra-Smashed/reflexion-skill", text)
        self.assertIn("thanisch.co", text)
        self.assertIn("/reflexion", text)

    def test_plugin_json(self):
        plugin = json.loads(read(ROOT, ".claude-plugin", "plugin.json"))
        market = json.loads(read(ROOT, ".claude-plugin", "marketplace.json"))
        self.assertEqual(plugin["name"], "reflexion-skill")
        self.assertEqual(market["plugins"][0]["name"], "reflexion-skill")
        self.assertEqual(plugin["author"]["url"], "https://thanisch.co")

    def test_python38_syntax(self):
        for path in text_dateien():
            if path.endswith(".py"):
                ast.parse(read(path), path, feature_version=(3, 8))


if __name__ == "__main__":
    unittest.main()
