"""把动作库媒体从 _ingest 拷到后端静态目录（一次性 / 换数据集时重跑）。

源：
  _ingest/exercises-dataset/videos/<id>-<media_id>.gif   动图 1324 个（123 MB）
  _ingest/exercises-dataset/publish/thumbs/<id>.jpg      缩略图 1324 张（12 MB）

目标：
  aio-backend/static/exercises/gifs/<id>.gif             只拷种子里的 1267 条
  aio-backend/static/exercises/thumbs/<id>.jpg           （删掉的 57 条不拷）

文件名统一改成 `<id>.gif` / `<id>.jpg`，与接口返回的 URL 一一对应，省掉映射表。
static/exercises 已在 .gitignore 里排除：媒体不进仓库，部署机上另拷一次。

用法：python scripts/copy_exercise_media.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
DATASET = REPO / "_ingest" / "exercises-dataset"
SEED = BACKEND / "data" / "exercises.seed.json"
OUT = BACKEND / "static" / "exercises"


def main() -> None:
    rows = json.loads(SEED.read_text(encoding="utf-8"))
    (OUT / "gifs").mkdir(parents=True, exist_ok=True)
    (OUT / "thumbs").mkdir(parents=True, exist_ok=True)

    gifs = thumbs = 0
    missing: list[str] = []
    for row in rows:
        ex_id, media_id = row["id"], row.get("media_id") or ""

        src_gif = DATASET / "videos" / f"{ex_id}-{media_id}.gif"
        dst_gif = OUT / "gifs" / f"{ex_id}.gif"
        if src_gif.exists():
            shutil.copyfile(src_gif, dst_gif)
            gifs += 1
        else:
            missing.append(f"gif {src_gif.name}")

        src_thumb = DATASET / "publish" / "thumbs" / f"{ex_id}.jpg"
        if src_thumb.exists():
            shutil.copyfile(src_thumb, OUT / "thumbs" / f"{ex_id}.jpg")
            thumbs += 1
        else:
            missing.append(f"thumb {src_thumb.name}")

    print(f"seed {len(rows)} 条 → gif {gifs} / thumb {thumbs}")
    if missing:
        print(f"缺失 {len(missing)} 个：{', '.join(missing[:10])}")


if __name__ == "__main__":
    main()
