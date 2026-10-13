"""Git checkpoints: a commit on every gate pass, resume from the last verified commit.

Each run owns a bare repository. The worker never sees it: the workspace is a
plain folder, and each lease epoch gets its own private workspace and index, so
a stale process cannot scribble into the folder its successor is using.
Promotion to ``refs/heads/verified`` is a compare-and-swap, a second fence on
top of the journal's lease epoch.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile

VERIFIED_REF = "refs/heads/verified"
_IDENT = {
    "GIT_AUTHOR_NAME": "urh",
    "GIT_AUTHOR_EMAIL": "urh@localhost",
    "GIT_COMMITTER_NAME": "urh",
    "GIT_COMMITTER_EMAIL": "urh@localhost",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
}


class CheckpointError(RuntimeError):
    pass


class GitCheckpoint:
    def __init__(self, run_dir: str):
        self.run_dir = os.path.abspath(run_dir)
        self.git_dir = os.path.join(self.run_dir, "repo.git")

    # ------------------------------------------------------------------ helpers
    def _git(self, *args: str, work_tree: str | None = None, index: str | None = None,
             input_bytes: bytes | None = None, check: bool = True) -> bytes:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(_IDENT)
        env["GIT_DIR"] = self.git_dir
        if work_tree is not None:
            env["GIT_WORK_TREE"] = work_tree
        if index is not None:
            env["GIT_INDEX_FILE"] = index
        proc = subprocess.run(["git", *args], env=env, input=input_bytes, capture_output=True,
                              cwd=work_tree or self.run_dir)
        if check and proc.returncode != 0:
            raise CheckpointError(f"git {' '.join(args)} failed: {proc.stderr.decode(errors='replace').strip()}")
        return proc.stdout

    def _index(self, epoch: int) -> str:
        return os.path.join(self.run_dir, f"index-e{epoch}")

    def workspace_path(self, epoch: int) -> str:
        return os.path.join(self.run_dir, f"work-e{epoch}")

    # ------------------------------------------------------------------ lifecycle
    def init(self, seed_dir: str | None = None) -> str:
        """Create the repo and the root commit (idempotent). Returns the root commit."""
        os.makedirs(self.run_dir, exist_ok=True)
        if not os.path.isdir(self.git_dir):
            subprocess.run(["git", "init", "--bare", "-q", self.git_dir], check=True, capture_output=True)
        head = self.verified_head()
        if head is not None:
            return head
        staging = os.path.join(self.run_dir, "seed-staging")
        shutil.rmtree(staging, ignore_errors=True)
        if seed_dir:
            shutil.copytree(seed_dir, staging, ignore=shutil.ignore_patterns(".git"))
        else:
            os.makedirs(staging)
        index = os.path.join(self.run_dir, "index-seed")
        self._git("add", "-A", ".", work_tree=staging, index=index)
        tree = self._git("write-tree", index=index).decode().strip()
        commit = self._git("commit-tree", tree, "-m", "urh: seed").decode().strip()
        self._git("update-ref", VERIFIED_REF, commit, "0" * 40)
        shutil.rmtree(staging, ignore_errors=True)
        os.unlink(index)
        return commit

    def verified_head(self) -> str | None:
        out = self._git("rev-parse", "-q", "--verify", VERIFIED_REF, check=False).decode().strip()
        return out or None

    def prepare_workspace(self, epoch: int, commit: str) -> str:
        """Materialize ``commit`` into a fresh private folder for this epoch."""
        path = self.workspace_path(epoch)
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path)
        index = self._index(epoch)
        if os.path.exists(index):
            os.unlink(index)
        self._git("read-tree", commit, index=index)
        self._git("checkout-index", "-a", "-f", work_tree=path, index=index)
        return path

    def reset_workspace(self, epoch: int, commit: str) -> str:
        return self.prepare_workspace(epoch, commit)

    def snapshot(self, epoch: int, parent: str, message: str) -> tuple[str, str]:
        """Stage everything in the epoch's workspace and write an unverified commit."""
        path = self.workspace_path(epoch)
        index = self._index(epoch)
        self._git("add", "-A", ".", work_tree=path, index=index)
        tree = self._git("write-tree", index=index).decode().strip()
        commit = self._git("commit-tree", tree, "-p", parent, "-m", message).decode().strip()
        return tree, commit

    def tree_of(self, commit: str) -> str:
        return self._git("rev-parse", f"{commit}^{{tree}}").decode().strip()

    def promote(self, commit: str, expected_parent: str) -> None:
        """Move the verified ref from ``expected_parent`` to ``commit``; fails if someone else moved it."""
        current = self.verified_head()
        if current == commit:
            return
        self._git("update-ref", VERIFIED_REF, commit, expected_parent)

    def changed_paths(self, old: str, new: str) -> list[str]:
        out = self._git("diff", "--name-only", "--no-renames", old, new).decode()
        return [p for p in out.splitlines() if p]

    def export(self, commit: str, dest: str) -> None:
        """Write the tree of ``commit`` into ``dest`` (for the gate's throwaway copy)."""
        os.makedirs(dest, exist_ok=True)
        data = self._git("archive", "--format=tar", commit)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dest, filter="data")

    def log(self, ref: str = VERIFIED_REF) -> list[tuple[str, str]]:
        out = self._git("log", "--format=%H%x00%s", ref).decode()
        return [tuple(line.split("\x00", 1)) for line in out.splitlines() if line]  # type: ignore[misc]

    def cleanup_epoch(self, epoch: int) -> None:
        shutil.rmtree(self.workspace_path(epoch), ignore_errors=True)
        try:
            os.unlink(self._index(epoch))
        except FileNotFoundError:
            pass
