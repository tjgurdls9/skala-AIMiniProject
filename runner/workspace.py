"""Policy-checked file operations on one isolated workspace; the model proposes, this module enforces."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile

from backend.contracts import SECRET, DomainError, digest, require

MAX_PATH = 200
MAX_FILE_BYTES = 65536
MAX_FILES = 200
VCS_DIR = ".git"


def relative_parts(name, allow_dot=False):
    """Validate a workspace-relative POSIX path and return its parts; '.' is only valid when allow_dot."""
    require(isinstance(name, str) and 0 < len(name) <= MAX_PATH, "FORBIDDEN", "작업 공간 안의 상대 경로가 필요합니다.", 403)
    require("\\" not in name and not any(ord(c) < 32 for c in name), "FORBIDDEN", "허용되지 않은 경로 문자입니다.", 403)
    path = PurePosixPath(name)
    require(str(path) == name and not path.is_absolute() and ".." not in path.parts and VCS_DIR not in path.parts,
            "FORBIDDEN", "작업 공간을 벗어나거나 저장소 내부를 가리키는 경로입니다.", 403)
    if name == ".":
        require(allow_dot, "FORBIDDEN", "파일 경로가 필요합니다.", 403)
        return ()
    return path.parts


def matches(name, patterns):
    return any(PurePosixPath(name).full_match(pattern) for pattern in patterns)


class Workspace:
    def __init__(self, root, write_scope=("**",)):
        self.root, self.write_scope = Path(root), tuple(write_scope)

    # -- path handling -------------------------------------------------
    def resolve(self, name, allow_dot=False):
        parts = relative_parts(name, allow_dot)
        require(not self.root.is_symlink(), "FORBIDDEN", "심볼릭 링크 작업 공간은 허용하지 않습니다.", 403)
        path = self.root
        for part in parts:
            path = path / part
            require(not path.is_symlink(), "FORBIDDEN", "심볼릭 링크는 허용하지 않습니다.", 403)
        require(path.resolve().is_relative_to(self.root.resolve()), "FORBIDDEN", "작업 공간을 벗어났습니다.", 403)
        return path

    def _writable(self, name):
        require(matches(name, self.write_scope), "FORBIDDEN", "현재 작업의 쓰기 범위 밖입니다.", 403)

    def _files(self):
        found = []
        for current, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d != VCS_DIR and not (Path(current) / d).is_symlink())
            for name in sorted(names):
                path = Path(current) / name
                if path.is_file() and not path.is_symlink():
                    found.append(path)
        return found

    # -- reads ---------------------------------------------------------
    def list_files(self):
        return [dict(path=p.relative_to(self.root).as_posix(), size=p.stat().st_size, content_digest=self._safe_digest(p))
                for p in self._files()]

    def read(self, name):
        path = self.resolve(name)
        require(path.is_file() and path.stat().st_size <= MAX_FILE_BYTES, "NOT_FOUND", "읽을 수 있는 작은 파일이 필요합니다.", 404)
        content = self._text(path)
        return dict(path=name, content=content, content_digest=digest(content))

    def manifest(self):
        return {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in self._files()}

    # -- mutations -----------------------------------------------------
    def write(self, name, content, expected_digest=None, enforce_scope=True):
        if enforce_scope:
            relative_parts(name)
            self._writable(name)
        require(isinstance(content, str) and len(content.encode()) <= MAX_FILE_BYTES and "\x00" not in content and not SECRET.search(content),
                "INVALID_COMMAND", "작은 비밀정보 없는 텍스트만 허용됩니다.", 422)
        path = self.resolve(name)
        current = self._digest(path) if path.exists() else None
        require(current == expected_digest, "VERSION_CONFLICT", "파일이 변경됐습니다. 다시 읽으세요.")
        require(current is not None or len(self._files()) < MAX_FILES, "INVALID_COMMAND", "작업 공간 파일 수 한도를 넘었습니다.", 422)
        self._replace(path, content)
        return dict(path=name, content_digest=digest(content), created=current is None)

    def delete(self, name, expected_digest):
        relative_parts(name)
        self._writable(name)
        path = self.resolve(name)
        require(path.is_file(), "NOT_FOUND", "삭제할 파일이 없습니다.", 404)
        previous = self._digest(path)
        require(previous == expected_digest, "VERSION_CONFLICT", "파일이 변경됐습니다. 다시 읽으세요.")
        path.unlink()
        return dict(path=name, previous_digest=previous)

    def move(self, source, target, expected_digest):
        for name in (source, target):
            relative_parts(name)
            self._writable(name)
        origin, destination = self.resolve(source), self.resolve(target)
        require(origin.is_file(), "NOT_FOUND", "이동할 파일이 없습니다.", 404)
        require(self._digest(origin) == expected_digest and not destination.exists(), "VERSION_CONFLICT",
                "파일이 변경됐거나 대상이 이미 있습니다.")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise DomainError("INVALID_COMMAND", "대상 경로를 만들 수 없습니다.", 422) from None
        os.replace(origin, destination)
        return dict(path=target, source=source, content_digest=expected_digest)

    def sanitize(self):
        """Remove symlinks and special files a sandboxed program left behind; the host later copies this tree, so a
        link that points at a host path must never survive a command."""
        removed = []
        for current, dirs, names in os.walk(self.root, followlinks=False):
            if VCS_DIR in dirs:
                dirs.remove(VCS_DIR)
            for name in list(dirs) + names:
                path = Path(current) / name
                if path.is_symlink() or (not path.is_dir() and not path.is_file()):
                    removed.append(path.relative_to(self.root).as_posix())
                    path.unlink()
            dirs[:] = [d for d in dirs if (Path(current) / d).exists() and not (Path(current) / d).is_symlink()]
        return sorted(removed)

    # -- helpers -------------------------------------------------------
    @staticmethod
    def _text(path):
        try:
            return path.read_text()
        except (UnicodeDecodeError, OSError):
            raise DomainError("NOT_FOUND", "UTF-8 텍스트 파일만 읽을 수 있습니다.", 404) from None

    @classmethod
    def _digest(cls, path):
        return digest(cls._text(path))

    @classmethod
    def _safe_digest(cls, path):
        try:
            return cls._digest(path)
        except DomainError:
            return None  # binary or oversized files are listed without a text digest

    @staticmethod
    def _replace(path, content):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as temp:
                temp.write(content)
                temporary = temp.name
        except OSError:
            raise DomainError("INVALID_COMMAND", "이 경로에는 파일을 쓸 수 없습니다.", 422) from None
        try:
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
