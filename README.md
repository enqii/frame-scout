# FrameScout – Local AI Image Search

FrameScout searches large local photo collections for motifs. Describe what you are
looking for (e.g. "red car", "golden retriever", "mountain landscape") and optionally add
example images; for each search profile FrameScout ranks the best matching photos and
shows them as a gallery.

- **Local:** your photos never leave your computer. Only model weights and Python
  packages are downloaded.
- **General-purpose:** people, objects, vehicles, animals, landscapes, scenes.
- **CPU is enough:** a dedicated GPU is optional (NVIDIA via CUDA).
- **Built on CLIP:** OpenAI CLIP ViT-B/32 by default, optionally combined with YOLO11n
  person detection for group photos. Search terms must be **English**.

> **Status:** prototype (v1.1) for Windows. Only one full search and one GPU run have been
> tested end to end; expect rough edges. Open issues: [BACKLOG.md](BACKLOG.md), plans:
> [ROADMAP.md](ROADMAP.md).

## Requirements

- Windows 10 (version 1803 or later) or Windows 11
- An internet connection for the installation and the first search
- No Python needed: the installer downloads its own copy

## Installation

1. Put the project into a folder of its own, e.g. `C:\FrameScout`:
   ```powershell
   git clone https://github.com/enqii/frame-scout.git C:\FrameScout
   ```
   (or download the ZIP and extract it).
2. Double-click `Install-FrameScout.bat`. It downloads a private Python into `.python`,
   creates `.venv` and installs the pinned dependencies. If it finds an NVIDIA driver,
   it offers GPU support (about 2.5 GB more download).

Do not move or rename the folder afterwards; if you did, run the installer again.
Details, GPU support and updating: [user guide](docs/USER-GUIDE.md#installation-details).

## Quick start

1. Double-click `Start-FrameScout.bat`. Your browser opens <http://127.0.0.1:8501>.
2. **Search profiles:** describe each motif in English (name, optional context, features,
   custom search texts) and optionally add reference images. Example profiles are
   included.
3. **Photo source:** enter one or more local photo folders; subfolders are included.
4. **AI settings:** keep the defaults, or choose another search model, the GPU or turn
   person detection off for motifs other than people.
5. **Search & results:** start the search, browse the ranked photos, mark matches and
   copy them to a folder. HTML galleries are written to `results/`.

Supported formats: JPG, PNG, WebP, BMP, TIFF, AVIF, HEIC/HEIF and common camera RAW
formats. Everything else, including what each setting does and how to clean up storage,
is in the [user guide](docs/USER-GUIDE.md).

## How reliable are the matches?

The score is a relative ranking value, **not a probability and not an identification**.
FrameScout can miss matches or return false ones, especially with large group photos,
small or inconspicuous motifs, and when comparing drawings or artwork with real photos.
Check the results before you rely on them.

## Uninstalling

Double-click `Uninstall-FrameScout.bat`. It deletes the environment, the private Python
and the caches after you confirm, and keeps your photos, profiles, settings and results.
Then delete the project folder yourself. Details:
[user guide](docs/USER-GUIDE.md#uninstalling-details).

## Documentation

- [User guide](docs/USER-GUIDE.md): every part of the app, file formats, results, storage
  cleanup, what the scores mean
- [Development](docs/DEVELOPMENT.md): command line, tests, model evaluation, project
  structure
- [Architecture](docs/ARCHITECTURE.md): internals for contributors
- [Security policy](SECURITY.md)

## License

FrameScout is licensed under the **GNU Affero General Public License v3.0**
(AGPL-3.0, see [LICENSE](LICENSE)). It comes without any warranty.

FrameScout installs and downloads third-party components that are not part of this
repository and keep their own licenses:

- **Ultralytics** and the YOLO11 person detector `yolo11n.pt` (AGPL-3.0), the main
  reason FrameScout itself uses the AGPL.
- **OpenCLIP** (MIT), **PyTorch** (BSD-3-Clause), **Streamlit** (Apache-2.0) and the
  other packages in `requirements.txt` and `constraints.txt`.
- **Model weights** of the search models, downloaded from the Hugging Face Hub on first
  use (`timm/vit_base_patch32_clip_224.openai`,
  `laion/CLIP-ViT-B-16-DataComp.XL-s13B-b90K`,
  `laion/CLIP-ViT-L-14-DataComp.XL-s13B-b90K`, `timm/ViT-B-16-SigLIP`), each under the
  license and terms on its model card.
