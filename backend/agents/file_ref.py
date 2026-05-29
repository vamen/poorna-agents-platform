"""FileRef — a lightweight reference to a file stored in FileService.

Agents never embed raw bytes in payloads.  Instead they receive/emit a
FileRef that the receiving agent can resolve via FileService.get().

Fields
------
file_id      Unique identifier assigned by FileService.put().
filename     Original filename (e.g. "photo.jpg").
mime_type    MIME type string (e.g. "image/jpeg").
size_bytes   File size in bytes.
backend      Storage backend tag: "local" | "s3".
uri          Opaque location string used internally by FileService
             (local path or s3://bucket/key).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FileRef:
    file_id: str
    filename: str
    mime_type: str
    size_bytes: int
    backend: str
    uri: str

    def to_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "backend": self.backend,
            "uri": self.uri,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FileRef":
        return cls(
            file_id=d["file_id"],
            filename=d["filename"],
            mime_type=d.get("mime_type", "application/octet-stream"),
            size_bytes=d.get("size_bytes", 0),
            backend=d.get("backend", "local"),
            uri=d["uri"],
        )
