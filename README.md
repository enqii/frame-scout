# FrameScout – Lokale KI-Bildsuche

FrameScout durchsucht große lokale Fotosammlungen nach Motiven. Du beschreibst, was du
suchst (z. B. „rotes Auto“, „Golden Retriever“, „Berglandschaft“), und gibst optional
Beispielbilder dazu. FrameScout erstellt daraus pro Suchprofil eine Rangliste der
passendsten Fotos als HTML-Galerie.

- **Lokal:** Eigene Bilder verlassen den Rechner nicht. Nur Modellgewichte und
  Python-Pakete werden bei der Installation bzw. beim ersten Lauf heruntergeladen.
- **Allgemein:** Personen, Objekte, Fahrzeuge, Tiere, Landschaften, Szenen.
- **Ohne Sprachmodell:** Die Suche basiert auf CLIP (ViT-B/32), optional ergänzt um
  YOLO11n-Personenerkennung für Gruppenfotos.

> **Status:** Prototyp (v1.1). Offene Punkte und Roadmap stehen in [BACKLOG.md](BACKLOG.md).

## Voraussetzungen

- Windows 10/11
- Python **3.14, 3.13 oder 3.12** mit `py`-Launcher (Installation über python.org)
- Internetverbindung für die Installation und den ersten Suchlauf
- Eine dedizierte GPU ist nicht nötig; die Suche läuft auch auf der CPU.

## Installation

1. Projekt in einen eigenen Ordner holen, z. B. `C:\FrameScout`:
   ```powershell
   git clone https://github.com/enqii/frame-scout.git C:\FrameScout
   ```
   (alternativ ZIP herunterladen und entpacken)
2. `Install-FrameScout.bat` doppelklicken. Der Installer sucht Python 3.14, 3.13 oder
   3.12 (in dieser Reihenfolge), legt eine isolierte `.venv` im Projektordner an und
   installiert die Abhängigkeiten.

Falls die Paketinstallation mit einer Python-Version scheitert: `.venv` löschen, eine
andere unterstützte Python-Version installieren und den Installer erneut starten.

## Start und Bedienung

1. `Start-FrameScout.bat` doppelklicken. Der Browser öffnet
   <http://127.0.0.1:8501>.
2. **Suchprofile:** Motiv benennen, optional Kontext, Merkmale (am besten auf Englisch),
   eigene Suchtexte und Referenzbilder angeben.
3. **Fotoquelle:** Lokalen Bildordner wählen (Standard: `photos` im Projektordner).
   Unterordner werden mit durchsucht. Archive und Online-Alben vorher selbst
   herunterladen und entpacken – FrameScout lädt keine Bilder aus dem Netz.
4. **KI-Einstellungen:** Mit „auto“ wird CUDA genutzt, falls PyTorch eine kompatible
   NVIDIA-GPU erkennt, sonst die CPU. Batchgröße 8 ist ein konservativer Startwert.
5. **Suche & Ergebnisse:** Analyse starten. Den Browser während des Suchlaufs möglichst
   offen lassen – Start/Stopp hängt an der laufenden Streamlit-Sitzung.

Unterstützte Formate: JPG, JPEG, PNG, WebP, BMP, TIF, TIFF.

## Ergebnisse

- Pro Suchprofil entsteht eine HTML-Galerie in `results/`, die Vorschaubilder liegen in
  `results/vorschaubilder/`. Ein Klick auf ein Foto öffnet das Original.
- Den Ordner `results` zusammenhalten: Eine einzeln exportierte HTML-Datei enthält keine
  Vorschaubilder, und die Links auf die Originale funktionieren nur auf diesem Rechner.
- Bereits analysierte Fotos werden in `results/cache.sqlite3` gespeichert. Ein
  abgebrochener Lauf setzt beim nächsten Start dort fort, und neue Suchprofile nutzen
  vorhandene Analysen wieder.

### Wie verlässlich sind die Treffer?

Die angezeigte „Ähnlichkeit“ ist ein relativer Ranking-Wert, **keine Wahrscheinlichkeit
und keine sichere Identifikation**. FrameScout kann Treffer übersehen oder falsche
Treffer liefern – besonders bei großen Gruppenfotos, kleinen oder unauffälligen Motiven
und beim Vergleich von Zeichnungen/Artwork mit echten Fotos. Die Personenerkennung hilft
bei Menschen in Gruppenbildern; für andere Motive kann sie abgeschaltet werden.

## Deinstallation

1. Ergebnisse und gewünschte Fotos an anderer Stelle sichern.
2. FrameScout schließen und den Projektordner löschen. Damit sind `.venv`, Caches
   (`.cache`, `.tmp`), Modellgewichte (inkl. `yolo11n.pt`) und Ergebnisse entfernt.

Eine systemweit installierte Python-Version bleibt bestehen. Einzelne Abhängigkeiten
können zusätzlich eigene Caches im Benutzerprofil anlegen.

## Entwicklung

Manueller Start nach der Installation:

```powershell
# Oberfläche
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501

# Engine direkt (CLI)
.\.venv\Scripts\python.exe framescout_engine.py .\photos --profiles .\profiles.json --output .\results --device cpu --batch-size 8 --top 150
```

Alle Optionen der Engine: `.\.venv\Scripts\python.exe framescout_engine.py --help`

### Projektstruktur

| Datei / Ordner | Zweck |
|---|---|
| `app.py` | Streamlit-Oberfläche (Profile, Fotoquelle, Einstellungen, Suchlauf) |
| `framescout_engine.py` | Such-Engine als eigenständige CLI |
| `profiles.json` | Gespeicherte Suchprofile |
| `requirements.txt` | Python-Abhängigkeiten |
| `Install-FrameScout.bat` / `Start-FrameScout.bat` | Installation und Start unter Windows |
| `BACKLOG.md` | Bekannte Schwachstellen und Roadmap |
| `photos/`, `references/`, `results/`, `run.log` | Nutzerdaten und Laufzeit-Ausgaben (nicht im Repo) |
| `.venv/`, `.cache/`, `.tmp/`, `yolo11n.pt` | Umgebung, Caches und Modellgewichte (nicht im Repo) |
