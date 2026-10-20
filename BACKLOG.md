# FrameScout – Backlog

Ergebnis der Code-Analyse vom 2026-10-20 (Stand v1.1). Punkte nach und nach abarbeiten
und hier abhaken. IDs (E = Engine, A = App, I = Installation/Projekt) werden in Commits
und Diskussionen referenziert.

## Status-Notiz

- `run.log` und `.venv` belegen einen vollständigen Lauf: Python 3.14.8, torch 2.14.1+cpu,
  4.997 Fotos, 6 Profile, 0 Fehler. `CLAUDE.md` behauptet noch, dass ein solcher Lauf
  nicht bestätigt sei → Doku anpassen.

## Bekannte Schwachstellen

### Engine (`framescout_engine.py`)

- [ ] **E1 – QuickGELU-Mismatch:** `create_model_and_transforms('ViT-B-32', pretrained='openai')`
      erzeugt die Warnung `QuickGELU mismatch`; die OpenAI-Gewichte laufen mit GELU statt
      QuickGELU → schlechtere Embeddings. Fix: `ViT-B-32-quickgelu` bzw. `force_quick_gelu=True`,
      `ENGINE`-Signatur erhöhen (Cache wird einmalig neu aufgebaut).
- [ ] **E2 – Kein Batching über Bilder:** `embed_images` erhält nur die Crops eines Fotos;
      die Batchgröße ist fast wirkungslos. Außerdem: kein paralleles Dekodieren, volle
      Auflösung (kein `Image.draft`), YOLO fest auf `device='cpu'`.
- [ ] **E3 – Deutsche Motivnamen in englischen Prompts:** z. B. „A photograph of Rotes Auto
      (Fahrzeuge)." – OpenAI-CLIP versteht praktisch nur Englisch, die UI-Platzhalter sind deutsch.
- [ ] **E4 – Maximum statt Mittelwert über Prompts:** rauschanfällig; ein generischer Prompt
      kann dominieren. Üblich ist ein gemitteltes Prompt-Ensemble.
- [ ] **E5 – Score-Skalen gemischt:** Text-Cosinus ≈ 0,2–0,35, Bild-Bild ≈ 0,5–0,9; die
      Referenzgewichtung wirkt dadurch deutlich stärker als nominell.
- [ ] **E6 – `path.stat()` außerhalb try** im Export (Zeile ~264): eine zwischenzeitlich
      gelöschte Datei bricht den gesamten HTML-Export ab.
- [ ] **E7 – Kein Aufräumen:** `vorschaubilder/`, `cache.sqlite3` (gelöschte Dateien, alte
      Signaturen) und HTML-Dateien umbenannter/gelöschter Profile wachsen unbegrenzt.
- [ ] **E8 – Cache-Key = absoluter Pfad:** Verschieben des Fotoordners erzwingt komplette
      Neuberechnung.
- [ ] **E9 – `yolo11n.pt` landet im Projektroot** statt in `.cache/`; nicht dokumentiert.
- [ ] **E10 – Duplikatprüfung vor `strip()`:** „Joker" und „ Joker" werden nicht als gleich erkannt.

### App (`app.py`)

- [ ] **A1 – Referenzbilder werden überschrieben:** Uploads heißen immer `reference-1…n`;
      ein zweiter Upload überschreibt die ersten. Profile mit gleichem Slug
      (z. B. „Rotes Auto"/„rotes-auto") teilen sich den Ordner.
- [ ] **A2 – `profiles.json`-Datenverlust:** `read_profiles` kennt das v3-Format nicht
      (liefert `[]`, nächstes Speichern überschreibt). JSON-Liste → `AttributeError`
      (nicht abgefangen). Kein Backup vor dem Speichern.
- [ ] **A3 – Slugs App ≠ Engine:** Engine hängt bei Kollision `-2` an und nutzt Hash-Fallback,
      App nutzt `profile` ohne Deduplizierung → Downloads fehlen/falsch zugeordnet.
      Umlaute fallen weg („Bär" → `b-r`).
- [ ] **A4 – Prozess-Handle nur in der Session:** Browser-Reload → Lauf verwaist, Stoppen
      unmöglich, Zweitstart möglich → zwei Prozesse schreiben in dieselbe `run.log`
      (wird geleert) und dieselbe SQLite-Datei („database is locked"). Gilt auch für mehrere Tabs.
- [ ] **A5 – Fortschritt nur für die Analysephase:** Scoring, Thumbnails und HTML-Export
      laufen danach ohne Anzeige bei vollem Balken.
- [ ] **A6 – Ordnerzählung bei jedem Rerun:** `rglob` über den gesamten Fotoordner bei jeder
      Interaktion; langsam bei großen Ordnern/Netzlaufwerken.
- [ ] **A7 – CUDA nie verfügbar:** pip installiert torch `+cpu`; „cuda" ist trotzdem wählbar.
- [ ] **A8 – UX-Lücken:** Profil löschen ohne Rückfrage; Einstellungen nur pro Session;
      Ergebnisse ohne Zeitstempel/Bezug zum Profilstand.
- [ ] **A9 – Kleinigkeiten:** doppeltes `import os`; `EXT` doppelt in App und Engine;
      `use_container_width` ggf. deprecated (Streamlit 1.66).

### Installation / Projekt

- [x] **I1 – Kein Git-Repository.** (erledigt 2026-10-20)
- [ ] **I2 – Keine Tests.**
- [ ] **I3 – `requirements.txt` ungepinnt;** keine CUDA-Option im Installer.
- [ ] **I4 – Installer setzt `py`-Launcher voraus;** ohne ihn irreführende Meldung
      „Python nicht gefunden".
- [ ] **I5 – Beispielprofile/Platzhalter cosplay-lastig** (Joker, Harley Quinn, 2B,
      „Batman / DC Comics") – widerspricht dem allgemeinen Produktziel.
- [ ] **I6 – `CLAUDE.md` aktualisieren** (erfolgreicher E2E-Lauf, siehe Status-Notiz).

## Roadmap (Priorität)

### P0 – Fundament und Korrektheit
- [x] Git-Repository + privates GitHub-Repo (I1)
- [ ] Gemeinsames Modul (z. B. `framescout_core.py`) für Slug, `EXT`, Profil-Laden/-Validierung (A3, A9)
- [ ] `pytest`-Tests ohne Modell-Download (I2)
- [ ] QuickGELU-Fix + `ENGINE`-Bump (E1)
- [ ] Datenverlust-Fixes: eindeutige Referenznamen (A1), robustes `read_profiles` + `.bak` (A2), E6

### P1 – Performance
- [ ] Batching über Bilder, paralleles Dekodieren, `Image.draft` (E2)
- [ ] Installer-Option für CUDA-torch, YOLO auf GPU (A7, I3)

### P2 – Robuste Läufe
- [ ] Engine schreibt Status-/Lock-Datei (PID, Phase, Fortschritt); App verbindet sich nach
      Reload wieder und verhindert Parallelstarts (A4, A5)
- [ ] Einstellungen in `settings.json` persistieren (A8)

### P3 – Suchqualität
- [ ] Prompt-Ensemble mitteln, Scores pro Profil normalisieren (E4, E5)
- [ ] Deutsch-Problem lösen: mehrsprachiges CLIP (`xlm-roberta-base-ViT-B-32`) oder explizites
      Feld „englischer Suchbegriff" (E3)
- [ ] Optional stärkere Modelle (ViT-B-16, ViT-L-14, SigLIP) mit CPU-Laufzeit-Hinweis

### P4 – UX
- [ ] Ergebnisgalerie in der App, Treffer markieren/in Ordner kopieren, „Ordner öffnen",
      ZIP-Export mit Thumbnails
- [ ] Cleanup von Cache/Thumbnails/verwaisten HTML-Dateien (E7); HEIC/RAW optional

### P5 – Distribution
- [ ] Gepinnte Abhängigkeiten, portable Python-Variante, Uninstall-Skript
