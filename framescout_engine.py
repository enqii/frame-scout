"""FrameScout: lokale Bildsuche mit CLIP und optionaler Personenerkennung.

Die Profile werden in profiles.json verwaltet. Referenzbilder sind optional.
Erster Modellstart benötigt Internet; eigene Bilder werden nicht hochgeladen.
"""
import argparse
import hashlib
import html
import io
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote

import numpy as np
import torch
import open_clip
from PIL import Image, ImageOps, ImageFile

Image.MAX_IMAGE_PIXELS = 160_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = True
EXT = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
ENGINE = 'v4-clip-vit-b-32-openai-yolo11n-crop-features-1'


def slugify(s):
    return re.sub('[^a-z0-9]+', '-', s.lower()).strip('-') or hashlib.sha256(s.encode()).hexdigest()[:10]


def open_image(path):
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert('RGB')


def load_profiles(filename, inline):
    raw = []
    if filename:
        data = json.loads(filename.read_text(encoding='utf-8-sig'))
        if isinstance(data, dict) and 'profiles' in data:
            raw = data['profiles']
        elif isinstance(data, dict):  # v3 migration: {name: [prompts, ...]}
            raw = [{'name': n, 'prompts': ps} for n, ps in data.items()]
        else:
            raise ValueError('JSON muss ein Objekt mit "profiles" sein (oder das bisherige v3-Format).')
        if not isinstance(raw, list):
            raise ValueError('"profiles" muss eine Liste sein.')
    for item in inline:
        fields = [s.strip() for s in item.split('|', 2)]
        raw.append({'name': fields[0], 'franchise': fields[1] if len(fields) > 1 else '',
                    'features': fields[2] if len(fields) > 2 else ''})
    if not raw:
        raise ValueError('Bitte --profiles oder mindestens ein --character angeben.')
    profiles = []
    names = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('Jedes Profil muss ein JSON-Objekt sein.')
        name = item.get('name', '')
        if not isinstance(name, str) or not name.strip() or name.lower() in names:
            raise ValueError(f'Profilname fehlt oder ist doppelt: {name!r}')
        names.add(name.lower())
        franchise = item.get('franchise', '')
        features = item.get('features', '')
        prompts = item.get('prompts', [])
        refs = item.get('reference_images', [])
        if not isinstance(franchise, str) or not isinstance(features, str) or not isinstance(prompts, list) or not isinstance(refs, list):
            raise ValueError(f'Ungueltiges Profil: {name}')
        if any(not isinstance(x, str) or not x.strip() for x in prompts + refs):
            raise ValueError(f'Prompts und Referenzbilder muessen nichtleere Zeichenketten sein: {name}')
        subject = name.strip()
        context = f' ({franchise.strip()})' if franchise.strip() else ''
        target = subject + context
        generated = [f'A photograph of {target}.',
                     f'An image showing {target}.',
                     f'A detailed photo of {target}.',
                     f'A scene featuring {target}.']
        if features.strip():
            generated += [f'A photograph of {target}, with {features.strip()}.',
                          f'An image showing {features.strip()}, depicting {target}.']
        profiles.append({'name': name.strip(), 'prompts': generated + prompts,
                         'refs': [((filename.parent if filename else Path.cwd()) / x).resolve() for x in refs]})
    return profiles


def crops_for(image, detector, limit, conf):
    crops = [('Gesamtbild', image)]
    if detector is None:
        return crops
    result = detector.predict(source=image, classes=[0], conf=conf, imgsz=640,
                              max_det=limit, verbose=False, device='cpu')[0]
    boxes = result.boxes.xyxy.cpu().tolist() if result.boxes is not None else []
    w, h = image.size
    for i, (x1, y1, x2, y2) in enumerate(boxes[:limit], 1):
        px, py = (x2 - x1) * .12, (y2 - y1) * .12
        x1, y1, x2, y2 = max(0, int(x1-px)), max(0, int(y1-py)), min(w, int(x2+px)), min(h, int(y2+py))
        if x2-x1 < 35 or y2-y1 < 70 or (x2-x1)*(y2-y1) > .92*w*h:
            continue
        crops.append((f'Person {i}', image.crop((x1, y1, x2, y2))))
    return crops


def pack(features):
    buf = io.BytesIO()
    np.save(buf, np.asarray(features, dtype=np.float16), allow_pickle=False)
    return buf.getvalue()


def unpack(blob):
    return np.load(io.BytesIO(blob), allow_pickle=False).astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description='FrameScout: Name, Referenzbilder, optionale Merkmale.')
    parser.add_argument('folder', type=Path, help='Fotoordner (Unterordner werden rekursiv durchsucht)')
    parser.add_argument('--profiles', type=Path, help='JSON mit Suchprofilen (siehe profiles.json)')
    parser.add_argument('--character', action='append', default=[], metavar='NAME|FRANCHISE|MERKMALE',
                        help='Beliebig oft nutzbar; z.B. "Rotes Auto|Fahrzeuge|red paint, black roof"')
    parser.add_argument('--output', type=Path, default=Path('results'))
    parser.add_argument('--device', choices=('auto', 'cpu', 'cuda'), default='auto')
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--top', type=int, default=150)
    parser.add_argument('--no-person-detection', action='store_true')
    parser.add_argument('--max-persons', type=int, default=12)
    parser.add_argument('--person-confidence', type=float, default=.3)
    parser.add_argument('--yolo-model', default='yolo11n.pt')
    parser.add_argument('--reference-weight', type=float, default=.35,
                        help='Gewichtung des Referenzbild-Scores (0..1); ohne Referenzbilder nur Text')
    args = parser.parse_args()
    if args.batch_size < 1 or args.top < 1 or args.max_persons < 1 or not (0 < args.person_confidence <= 1) or not (0 <= args.reference_weight <= 1):
        parser.error('Ungueltiger Wert fuer batch-size, top, max-persons, person-confidence oder reference-weight.')
    root = args.folder.resolve()
    output = args.output.resolve()
    if not root.is_dir():
        parser.error(f'Fotoordner existiert nicht: {root}')
    if output == root:
        parser.error('Ausgabeordner darf nicht identisch mit Fotoordner sein.')
    try:
        profiles = load_profiles(args.profiles.resolve() if args.profiles else None, args.character)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    for p in profiles:
        for ref in p['refs']:
            if not ref.is_file():
                parser.error(f'Referenzbild fehlt: {ref}')
    paths = sorted(x for x in root.rglob('*') if x.is_file() and x.suffix.lower() in EXT and output not in x.parents)
    if not paths:
        parser.error('Keine unterstützten Bilder gefunden. Bitte den lokalen Bildordner prüfen.')
    device = ('cuda' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else args.device
    if device == 'cuda' and not torch.cuda.is_available():
        parser.error('CUDA ist nicht verfuegbar; --device cpu verwenden.')
    torch.set_num_threads(min(12, max(1, torch.get_num_threads())))
    output.mkdir(parents=True, exist_ok=True)
    print(f'{len(paths)} Fotos; {len(profiles)} Suchprofile; CLIP: {device}; YOLO: {not args.no_person_detection}', flush=True)
    print('Beim ersten Start werden die Modellgewichte heruntergeladen.', flush=True)
    model, _, preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='openai', device=device)
    model.eval()
    tokenizer = open_clip.get_tokenizer('ViT-B-32')

    def embed_images(images):
        vectors = []
        with torch.inference_mode():
            for start in range(0, len(images), args.batch_size):
                batch = torch.stack([preprocess(im) for im in images[start:start+args.batch_size]]).to(device)
                emb = model.encode_image(batch).float()
                emb /= emb.norm(dim=-1, keepdim=True).clamp_min(1e-8)
                vectors.append(emb.cpu().numpy())
        return np.concatenate(vectors, axis=0)

    profile_vectors = {}
    with torch.inference_mode():
        for p in profiles:
            t = model.encode_text(tokenizer(p['prompts']).to(device)).float()
            t /= t.norm(dim=-1, keepdim=True).clamp_min(1e-8)
            ref_vectors = []
            for ref in p['refs']:
                try:
                    ref_vectors.append(embed_images([open_image(ref)])[0])
                except Exception as exc:
                    parser.error(f'Referenzbild unlesbar ({ref}): {exc}')
            profile_vectors[p['name']] = (t.cpu().numpy(), np.asarray(ref_vectors, dtype=np.float32) if ref_vectors else None)

    detector = None
    if not args.no_person_detection:
        from ultralytics import YOLO
        detector = YOLO(args.yolo_model)
    config = [ENGINE, not args.no_person_detection, args.max_persons, args.person_confidence,
              args.yolo_model]
    signature = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    con = sqlite3.connect(output / 'cache.sqlite3')
    con.execute('''CREATE TABLE IF NOT EXISTS features (
        path TEXT NOT NULL, signature TEXT NOT NULL, mtime_ns INTEGER NOT NULL,
        size INTEGER NOT NULL, labels TEXT NOT NULL, vectors BLOB NOT NULL,
        PRIMARY KEY(path, signature))''')
    con.commit()
    fresh = reused = errors = 0
    try:
        for n, path in enumerate(paths, 1):
            try:
                stat = path.stat()
                record = con.execute('SELECT mtime_ns,size FROM features WHERE path=? AND signature=?', (str(path), signature)).fetchone()
                if record == (stat.st_mtime_ns, stat.st_size):
                    reused += 1
                else:
                    crops = crops_for(open_image(path), detector, args.max_persons, args.person_confidence)
                    labels = [label for label, _ in crops]
                    vec = embed_images([im for _, im in crops])
                    con.execute('INSERT OR REPLACE INTO features VALUES (?,?,?,?,?,?)',
                                (str(path), signature, stat.st_mtime_ns, stat.st_size,
                                 json.dumps(labels, ensure_ascii=False), pack(vec)))
                    con.commit()
                    fresh += 1
            except Exception as exc:
                errors += 1
                print(f'FEHLER {path}: {exc}', flush=True)
            if n % 25 == 0 or n == len(paths):
                print(f'{n}/{len(paths)} | Neu: {fresh} | Cache: {reused} | Fehler: {errors}', flush=True)
    except KeyboardInterrupt:
        print('\nUnterbrochen: bereits bearbeitete Bilder sind im Cache. Einfach erneut starten.')
        con.close()
        return 130

    scores = {p['name']: [] for p in profiles}
    for path in paths:
        try:
            stat = path.stat()
            record = con.execute('SELECT mtime_ns,size,labels,vectors FROM features WHERE path=? AND signature=?',
                                 (str(path), signature)).fetchone()
            if record is None or record[:2] != (stat.st_mtime_ns, stat.st_size):
                continue
            labels = json.loads(record[2]); features = unpack(record[3])
            features /= np.maximum(np.linalg.norm(features, axis=1, keepdims=True), 1e-8)
            for p in profiles:
                texts, refs = profile_vectors[p['name']]
                text_scores = (features @ texts.T).max(axis=1)
                if refs is not None:
                    visual_scores = (features @ refs.T).max(axis=1)
                    combined = (1-args.reference_weight) * text_scores + args.reference_weight * visual_scores
                else:
                    combined = text_scores
                best = int(np.argmax(combined))
                scores[p['name']].append((float(combined[best]), path, labels[best]))
        except Exception as exc:
            print(f'CACHE-FEHLER {path}: {exc}', flush=True)
    con.close()

    thumbs = output / 'vorschaubilder'; thumbs.mkdir(exist_ok=True)
    slugs = {}; used = set()
    for p in profiles:
        base = slugify(p['name']); slug = base; n = 2
        while slug in used:
            slug = f'{base}-{n}'; n += 1
        used.add(slug); slugs[p['name']] = slug
    nav = '<nav>' + ' · '.join(f'<a href="{quote(slugs[p["name"]] + ".html")}">{html.escape(p["name"])}</a>' for p in profiles) + '</nav>'
    style = '''body{font:16px system-ui;background:#181818;color:#eee;margin:24px}a{color:#a9d2ff}
    main{display:grid;grid-template-columns:repeat(auto-fill,minmax(225px,1fr));gap:16px}
    article{background:#292929;padding:12px;border-radius:10px;overflow-wrap:anywhere}
    img{width:100%;height:250px;object-fit:contain;background:#111;border-radius:5px}
    small{color:#bbb}nav{margin-bottom:22px}'''
    for p in profiles:
        name = p['name']; ranked = sorted(scores[name], key=lambda x: x[0], reverse=True)[:args.top]
        cards = []
        for rank, (score, path, label) in enumerate(ranked, 1):
            thumb_name = hashlib.sha256((str(path)+str(path.stat().st_mtime_ns)).encode()).hexdigest()[:24]+'.jpg'
            thumb = thumbs / thumb_name
            try:
                if not thumb.exists():
                    im = open_image(path); im.thumbnail((380, 380)); im.save(thumb, quality=82)
            except Exception as exc:
                print(f'Vorschaubild nicht moeglich ({path}): {exc}', flush=True)
                continue
            uri = html.escape(path.as_uri(), quote=True)
            rel = html.escape(str(path.relative_to(root)))
            cards.append(f'<article><a href="{uri}" target="_blank"><img loading="lazy" src="vorschaubilder/{quote(thumb_name)}" alt="{rel}"></a>'
                         f'<p><b>#{rank}</b> · Ähnlichkeit {score:.3f} · {html.escape(label)}<br>'
                         f'<a href="{uri}" target="_blank">{html.escape(path.name)}</a></p><small>{rel}</small></article>')
        page = ('<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>FrameScout – {html.escape(name)}</title><style>{style}</style>' + nav +
                f'<h1>{html.escape(name)} – Top {len(cards)}</h1><p>Automatisch erzeugte Rangliste, keine garantierte Identifikation. '
                'Gesamtbild oder Person bezeichnet den höchstbewerteten Ausschnitt. Zum Original auf ein Foto klicken.</p><main>' + ''.join(cards) + '</main></html>')
        target = output / (slugs[name] + '.html'); target.write_text(page, encoding='utf-8')
        print(f'{name}: {target}', flush=True)
    print(f'Fertig. Neue Fotoanalysen: {fresh}, Cache: {reused}. Weitere Suchprofile können den bestehenden Cache wiederverwenden.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
