from __future__ import annotations

import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": message}


class FilesystemTools:
    def __init__(self, workspace_root: str | Path, max_output_chars: int = 20_000) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.max_output_chars = max_output_chars

    def _resolve(self, path: str) -> Path:
        candidate = (self.workspace_root / path).resolve()
        if not candidate.is_relative_to(self.workspace_root):
            raise ValueError("path escapes workspace")
        return candidate

    def list_dir(self, path: str) -> dict[str, Any]:
        try:
            target = self._resolve(path)
            if not target.is_dir():
                return _error("directory does not exist")
            entries = []
            for item in sorted(target.iterdir(), key=lambda value: value.name.lower()):
                entries.append(
                    {
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    }
                )
            return _ok({"path": path, "entries": entries})
        except ValueError as exc:
            return _error(str(exc))

    def read_file(self, path: str) -> dict[str, Any]:
        try:
            target = self._resolve(path)
            if not target.is_file():
                return _error("file does not exist")
            content = target.read_text(encoding="utf-8")
            truncated = len(content) > self.max_output_chars
            return _ok(
                {
                    "path": path,
                    "content": content[: self.max_output_chars],
                    "truncated": truncated,
                }
            )
        except (UnicodeDecodeError, ValueError) as exc:
            return _error(str(exc))

    def search_content(self, keyword: str, dir: str) -> dict[str, Any]:
        if not keyword:
            return _error("keyword is required")
        try:
            target = self._resolve(dir)
            if not target.is_dir():
                return _error("directory does not exist")
            matches = []
            for file_path in sorted(target.rglob("*")):
                if not file_path.is_file():
                    continue
                try:
                    lines = file_path.read_text(encoding="utf-8").splitlines()
                except (OSError, UnicodeDecodeError):
                    continue
                for line_number, text in enumerate(lines, start=1):
                    if keyword.casefold() in text.casefold():
                        matches.append(
                            {
                                "path": file_path.relative_to(self.workspace_root).as_posix(),
                                "line": line_number,
                                "text": text[:500],
                            }
                        )
                        if len(matches) >= 100:
                            return _ok({"matches": matches, "truncated": True})
            return _ok({"matches": matches, "truncated": False})
        except ValueError as exc:
            return _error(str(exc))

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        try:
            target = self._resolve(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            encoded = content.encode("utf-8")
            target.write_bytes(encoded)
            return _ok(
                {
                    "path": target.relative_to(self.workspace_root).as_posix(),
                    "bytes_written": len(encoded),
                }
            )
        except ValueError as exc:
            return _error(str(exc))

    def bash(self, command: str) -> dict[str, Any]:
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return _error(str(exc))
        if not parts:
            return _error("command is required")

        if parts[0] == "echo":
            return _ok({"stdout": " ".join(parts[1:]) + "\n", "stderr": "", "exit_code": 0})
        if parts == ["pwd"]:
            return _ok({"stdout": f"{self.workspace_root}\n", "stderr": "", "exit_code": 0})
        if parts == ["date"]:
            return _ok({"stdout": f"{datetime.now().isoformat()}\n", "stderr": "", "exit_code": 0})
        if parts[0] == "ls" and len(parts) <= 2:
            path = parts[1] if len(parts) == 2 else "."
            result = self.list_dir(path)
            if not result["ok"]:
                return result
            names = [entry["name"] for entry in result["data"]["entries"]]
            return _ok({"stdout": "\n".join(names) + ("\n" if names else ""), "stderr": "", "exit_code": 0})
        if parts == ["git", "status"]:
            completed = subprocess.run(
                ["git", "status", "--short"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=5,
                shell=False,
            )
            return _ok(
                {
                    "stdout": completed.stdout[:8_000],
                    "stderr": completed.stderr[:8_000],
                    "exit_code": completed.returncode,
                }
            )
        return _error("command is not allowed")

