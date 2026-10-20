FRAMESCOUT - Lokale KI-Bildsuche (Streamlit)
==========================================

1. ZIP in einen eigenen Ordner entpacken (z. B. C:\FrameScout).
2. Beliebige Bildsammlungen lokal bereitstellen (z. B. im Unterordner photos).
   Archive vorab entpacken; FrameScout lädt Bilder nicht von Online-Diensten herunter.
3. Unter Windows Install-FrameScout.bat doppelklicken. Der Installer sucht Python
   3.14, 3.13 oder 3.12 und erstellt eine isolierte .venv im Projektordner.
   Falls die Paketinstallation mit einer Version scheitert: .venv löschen und
   nach Installation einer alternativen Python-Version erneut installieren.
4. Start-FrameScout.bat öffnen. Browser: http://127.0.0.1:8501
5. Suchprofile verwalten, lokalen Bildordner auswählen, Einstellungen kontrollieren
   und die Analyse starten. Mit »Automatisch« wird CUDA genutzt, falls verfügbar,
   ansonsten die CPU. Batchgröße 8 ist ein konservativer Ausgangswert.
6. Die HTML-Galerien liegen in results (mit Unterordner vorschaubilder).
   Beim Export einer einzelnen HTML-Datei fehlen die separat gespeicherten
   Vorschaubilder; für die komplette Galerie den Ergebnisordner zusammenhalten.

Beim ersten Lauf wird CLIP ViT-B/32 und bei eingeschalteter Personenerkennung
YOLO11n heruntergeladen. Kein generatives Sprachmodell nötig; eigene Bilder
bleiben lokal. Die Erkennung erzeugt eine Rangliste und kann Treffer übersehen.
Personenerkennung ist für Menschen/Gruppenbilder nützlich, für andere Motive
optional. Bereits analysierte Dateien werden in results/cache.sqlite3 gespeichert.

Nach Gebrauch Ergebnisse und gewünschte Fotos separat sichern, Anwendung
schließen und den Projektordner löschen. Eine systemweite Python-Installation
bleibt bestehen. Einige Abhängigkeiten können eigene Benutzer-Caches anlegen.
Die Start/Stopp-Steuerung verwaltet die Analyse in der laufenden Streamlit-Sitzung;
den Browser während eines Suchlaufs möglichst offen lassen.
