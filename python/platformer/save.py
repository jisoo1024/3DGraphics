"""Versioned, defensive JSON saves with same-directory atomic replacement."""
import json
import math
import os
from pathlib import Path
import tempfile
import time

from .config import DEFAULT_OPTIONS
from .inventory import CATALOG


VERSION = 1


def default_path():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "ForestOfPatience" / "save.json"


def defaults():
    return {"version": VERSION, "meso": 0, "owned": [], "equipped": {},
            "best_time": None, "options": dict(DEFAULT_OPTIONS)}


def number(value, fallback, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return fallback
    return max(low, min(high, value))


def validate(data):
    out = defaults()
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != VERSION:
        raise ValueError("지원하지 않는 저장 데이터 버전")
    out["meso"] = int(number(data.get("meso"), 0, 0, 1_000_000_000))
    owned = data.get("owned", [])
    if isinstance(owned, list):
        out["owned"] = list(dict.fromkeys(x for x in owned if isinstance(x, str) and x in CATALOG))
    equipped = data.get("equipped", {})
    if isinstance(equipped, dict):
        out["equipped"] = {slot: item for slot, item in equipped.items()
                           if isinstance(item, str) and item in out["owned"]
                           and CATALOG[item].slot == slot}
    best = data.get("best_time")
    if isinstance(best, (int, float)) and not isinstance(best, bool) and math.isfinite(best) and best > 0:
        out["best_time"] = best
    options = data.get("options", {})
    if isinstance(options, dict):
        for key in ("bgm", "sfx"):
            out["options"][key] = number(options.get(key), DEFAULT_OPTIONS[key], 0, 1)
        out["options"]["sensitivity"] = number(options.get("sensitivity"), 1, 0.2, 3)
        if isinstance(options.get("shadows"), bool):
            out["options"]["shadows"] = options["shadows"]
    return out


class SaveStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_path()
        self.notice = ""

    def load(self):
        if not self.path.exists():
            return defaults()
        try:
            return validate(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, OverflowError):
            self.notice = "저장 파일을 읽을 수 없어 기본값으로 시작합니다."
            try:
                backup = self.path.with_name(f"save.corrupt-{time.time_ns()}.json")
                self.path.rename(backup)
                self.notice += " 원본은 백업했습니다."
            except OSError:
                pass
            return defaults()

    def write(self, profile):
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix="save-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(validate(profile), stream, ensure_ascii=False, allow_nan=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            return True
        except (OSError, ValueError, TypeError):
            self.notice = "저장하지 못했습니다. 저장 경로의 권한을 확인해 주세요."
            return False
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
