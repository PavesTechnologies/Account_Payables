# Backend/Business_Layer/utils/local_drive_client.py
"""Local-folder stand-in for GraphDriveClient, for testing the bulk-import pickup without
SharePoint (6.7). Same layout and the same five calls the pickup uses, so the import, checks and
auto-recording behave exactly as with SharePoint:

    <folder>/Payments/Inbox        sheet(s) + receipts
    <folder>/TDS Challans/Inbox    sheet(s) + challans
    <folder>/TDS Filings/Inbox     sheet(s) + acknowledgements
    .../<type>/Processed/<date>/   processed files + "<sheet> - results.xlsx"

Default folder: Backend/local_imports (git-ignored - receipts are financial documents and must not
be committed). Override with LOCAL_IMPORT_FOLDER or `--local <path>`.
"""
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_FOLDER = Path(__file__).resolve().parents[2] / "local_imports"


class LocalDriveClient:
    def __init__(self, folder: Optional[str] = None):
        self.root = Path(folder or os.environ.get("LOCAL_IMPORT_FOLDER") or DEFAULT_FOLDER).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _inside(self, path: Path) -> Path:
        resolved = path.resolve()
        if self.root != resolved and self.root not in resolved.parents:
            raise ValueError("Path is outside the import folder")
        return resolved

    def children(self, folder: str) -> List[Dict[str, Any]]:
        directory = self._inside(self.root / folder)
        if not directory.is_dir():
            return []
        items = []
        for entry in sorted(directory.iterdir()):
            if not entry.is_file() or entry.name.startswith(("~$", ".")):  # skip Excel lock / hidden files
                continue
            stat = entry.stat()
            items.append({
                "id": f"local:{entry}",
                "name": entry.name,
                "eTag": f"{stat.st_mtime_ns}-{stat.st_size}",  # a saved edit = a new version
                "size": stat.st_size,
                "file": {},
                "lastModifiedBy": {"user": {"displayName": "Local folder"}},
            })
        return items

    def _path(self, item_id: str) -> Path:
        return self._inside(Path(item_id[len("local:"):] if item_id.startswith("local:") else item_id))

    def download(self, item_id: str) -> bytes:
        return self._path(item_id).read_bytes()

    def ensure_folder(self, path: str) -> str:
        directory = self._inside(self.root / path)
        directory.mkdir(parents=True, exist_ok=True)
        return str(directory)

    def move(self, item_id: str, folder_id: str, new_name: Optional[str] = None) -> None:
        source = self._path(item_id)
        target_dir = self._inside(Path(folder_id))
        target = target_dir / (new_name or source.name)
        counter = 1
        while target.exists():  # same as SharePoint's conflictBehavior=rename
            target = target_dir / f"{target.stem} ({counter}){target.suffix}"
            counter += 1
        shutil.move(str(source), str(target))

    def upload(self, folder_id: str, name: str, content: bytes) -> None:
        (self._inside(Path(folder_id)) / name).write_bytes(content)
