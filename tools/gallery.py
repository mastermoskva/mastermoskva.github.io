"""
Обработка галереи работ. Запускается автоматически на GitHub (см. .github/workflows/site.yml).

Что делает:
  1. Берёт все фото из папок works/<категория>/ (jpg, png, heic, webp).
  2. Новые фото переводит в JPG, уменьшает до 1600px и даёт им простое имя (mebel-007.jpg).
     Исходное имя файла становится подписью (IMG_1234 и подобные — без подписи).
  3. Делает превью в thumbs/<категория>/.
  4. Обновляет works.json — список работ для сайта. Новые работы встают в начало.
     Подписи и порядок, которые вы поправили в works.json вручную, сохраняются.
  5. Удалённые фото пропадают из списка, их превью удаляются.
"""
import json
import re
from pathlib import Path

from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
WORKS = ROOT / "works"
THUMBS = ROOT / "thumbs"
MANIFEST = ROOT / "works.json"

CATEGORIES = {
    "mebel": "Мебель",
    "vannaya": "Ванная",
    "montazh": "Монтаж и электрика",
}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
FULL_SIZE = 1600
THUMB_SIZE = 640
NAME_RE = re.compile(r"^(?P<cat>[a-z]+)-(?P<n>\d{3,})\.jpg$")


def auto_title(stem):
    """Подпись из имени файла: «Шкаф-купе (2)» → «Шкаф-купе»; IMG_2968 → пусто."""
    s = re.sub(r"[_]+", " ", stem).strip()
    s = re.sub(r"\s*\(\d+\)$", "", s)          # «(2)» в конце
    s = re.sub(r"\s+(copy|копия)(\s*\d+)?$", "", s, flags=re.I)
    if re.match(r"^(img|dsc|dscn|photo|pxl|image|fullsizerender|whatsapp image)[\s\-]?\d", s, re.I):
        return ""
    if re.fullmatch(r"[\d\s\-.]+", s):
        return ""
    return s[:1].upper() + s[1:]


def next_number(cat_dir, cat):
    nums = [int(m["n"]) for p in cat_dir.iterdir() if (m := NAME_RE.match(p.name)) and m["cat"] == cat]
    return max(nums, default=0) + 1


def save_jpeg(img, path, size, quality):
    img = img.copy()
    img.thumbnail((size, size), Image.LANCZOS)
    img.save(path, "JPEG", quality=quality, optimize=True, progressive=True)
    return img.size


def main():
    old = []
    if MANIFEST.exists():
        try:
            old = json.loads(MANIFEST.read_text(encoding="utf-8")).get("items", [])
        except (ValueError, AttributeError):
            print("works.json повреждён — собираю заново (подписи, исправленные вручную, могут потеряться)")
    by_file = {it["file"]: it for it in old if isinstance(it, dict) and "file" in it}

    new_items = []
    seen = set()
    for cat in CATEGORIES:
        cat_dir = WORKS / cat
        cat_dir.mkdir(parents=True, exist_ok=True)
        (THUMBS / cat).mkdir(parents=True, exist_ok=True)
        for src in sorted(cat_dir.iterdir(), key=lambda p: p.name):
            if src.name.startswith(".") or src.suffix.lower() not in IMAGE_EXT:
                continue
            title = None
            if not NAME_RE.match(src.name) or NAME_RE.match(src.name)["cat"] != cat:
                # новое фото: конвертируем и переименовываем
                try:
                    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
                except Exception as e:  # битый файл — пропускаем, но не падаем
                    print(f"Не удалось открыть {src}: {e}")
                    continue
                dst = cat_dir / f"{cat}-{next_number(cat_dir, cat):03d}.jpg"
                save_jpeg(img, dst, FULL_SIZE, 82)
                title = auto_title(src.stem)
                src.unlink()
                print(f"Новое фото: {src.name} → {dst.name}  «{title}»")
                src = dst
            rel = f"works/{cat}/{src.name}"
            thumb = THUMBS / cat / src.name
            if not thumb.exists():
                with Image.open(src) as im:
                    save_jpeg(im.convert("RGB"), thumb, THUMB_SIZE, 78)
            with Image.open(thumb) as t:
                w, h = t.size
            seen.add(rel)
            if rel in by_file:
                it = by_file[rel]
                it.update({"thumb": f"thumbs/{cat}/{src.name}", "cat": cat, "w": w, "h": h})
                it.setdefault("title", "")
                it.setdefault("note", "")
            else:
                new_items.append({"file": rel, "thumb": f"thumbs/{cat}/{src.name}", "cat": cat,
                                  "title": title or "", "note": "", "w": w, "h": h})

    # удаляем превью фото, которых больше нет
    for t in THUMBS.glob("*/*"):
        if f"works/{t.parent.name}/{t.name}" not in seen:
            t.unlink()
            print(f"Удалено превью: {t}")

    kept = [it for it in old if isinstance(it, dict) and it.get("file") in seen]
    items = new_items[::-1] + kept   # новые — в начало (последнее загруженное — первым)

    lines = ",\n".join("    " + json.dumps(it, ensure_ascii=False) for it in items)
    cats = json.dumps(CATEGORIES, ensure_ascii=False)
    MANIFEST.write_text('{\n  "categories": ' + cats + ',\n  "items": [\n' + lines + "\n  ]\n}\n", encoding="utf-8")
    print(f"Готово: {len(items)} работ, новых {len(new_items)}")


if __name__ == "__main__":
    main()
