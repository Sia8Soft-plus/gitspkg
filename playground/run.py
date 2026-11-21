"""Use the real CLI with filesystem-backed demo transport, without system install."""

import io
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys


REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".playground"
REMOTE_PREFIX = PurePosixPath("/date/gits/base_lean")


def local_remote(path):
    relative = PurePosixPath(str(path)).relative_to(REMOTE_PREFIX)
    result = (STATE / "remote" / str(relative)).resolve()
    result.relative_to((STATE / "remote").resolve())
    return result


class FixtureSFTP:
    def listdir_attr(self, path):
        from paramiko import SFTPAttributes
        return [SFTPAttributes.from_stat(item.stat(), filename=item.name)
                for item in sorted(local_remote(path).iterdir())]

    def stat(self, path):
        return local_remote(path).stat()

    def open(self, path, mode="r"):
        if mode not in ("r", "rb"):
            raise PermissionError("Demo remote is read-only")
        return local_remote(path).open("rb")

    def get(self, remote, destination, callback=None):
        source = local_remote(remote)
        destination = Path(destination).resolve()
        roots = ((STATE / "lean").resolve(), (STATE / "project").resolve())
        if not any(destination.is_relative_to(root) for root in roots):
            raise PermissionError("Demo downloads must stay in the sandbox")
        shutil.copy2(source, destination)
        if callback:
            callback(source.stat().st_size, source.stat().st_size)

    def close(self):
        pass


class FixtureSSH:
    def exec_command(self, command):
        # Recognize only the CLI's fixed archive-index query; never invoke a shell.
        match = re.fullmatch(
            r'find (/date/gits/base_lean/[A-Za-z0-9_./-]+) -type f '
            r'\\\( -name "\*\.zip" -o -name "\*\.tar" \\\) -printf "%p\|%T@\\n"',
            command)
        if not match:
            raise PermissionError("Unsupported demo index query")
        root = local_remote(match.group(1))
        lines = []
        for archive in sorted(root.rglob("*")):
            if archive.is_file() and archive.suffix in (".zip", ".tar"):
                path = REMOTE_PREFIX / archive.relative_to(STATE / "remote").as_posix()
                lines.append(f"{path}|{archive.stat().st_mtime}\n")
        return io.BytesIO(), io.BytesIO("".join(lines).encode()), io.BytesIO()

    def close(self):
        pass


def main():
    if not (STATE / "runtime" / "main.py").exists():
        raise SystemExit("Run playground/bootstrap.py first")
    sys.path.insert(0, str(STATE / "runtime"))
    import main as cli
    from gits import commands, lean

    args, remaining = cli.parse_args()
    allowed = args.command == "version" or (
        args.command == "check" and args.import_check and not args.argument and not remaining)
    allowed = allowed or (
        args.command in ("status", "update") and args.lean and not args.dep
        and not args.argument and not args.spec and not args.obj_name and not remaining
        and args.to_destination is None
        and (not args.manifest_filename or args.manifest_filename == "setup.manifest")
        and (args.command != "update" or bool(args.specific) or args.no_obj))
    if not allowed:
        raise SystemExit("Demo supports version, check --import, status --lean, and update --lean (--no-obj or --specific).")

    os.chdir(STATE / "project")
    commands.before_check = lambda unused: True
    lean.get_sftp_session = lambda: FixtureSFTP()
    lean._GLOBAL_SSH = FixtureSSH()
    lean.get_local_os_info = lambda: ("linux", "12")
    lean.get_vs_version = lambda: "[GCC]"
    # Confine any environment changes to this process, including packages requested directly.
    lean.add_to_system_path_env = lambda path: None
    print("PLAYGROUND: local fixture transport; no SSH authentication or real inference.")
    commands.cmds(args, remaining)


if __name__ == "__main__":
    main()
