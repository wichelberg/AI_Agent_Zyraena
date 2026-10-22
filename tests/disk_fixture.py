"""A fake drive for the disk tests: a temporary folder laid out like C: (Windows, Program Files, a
Steam library, a user folder with AppData, caches, venvs, projects, _MEI leftovers), with fake
Sources for the registry, shortcuts and git. Nothing outside the temporary folder is read or touched.
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import disk_tools  # noqa: E402

KB = 1024


def write(path, size=4 * KB, text=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if text is not None:
        path.write_text(text, encoding="utf-8")
    else:
        path.write_bytes(b"x" * size)
    return path


def make_venv(folder, version="3.11.9", home="", packages=(), pth=()):
    folder = Path(folder)
    write(folder / "pyvenv.cfg", text=f"home = {home}\ninclude-system-site-packages = false\nversion = {version}\n")
    site = folder / "Lib" / "site-packages"
    write(site / "big.bin", 64 * KB)
    for name in packages:
        (site / f"{name}-1.0.dist-info").mkdir(parents=True, exist_ok=True)
    for i, target in enumerate(pth):
        write(site / f"link{i}.pth", text=f"# added by a test\nimport os\n{target}\n")
    return folder


class FakeSources(disk_tools.Sources):
    def __init__(self, tree):
        self.tree = tree
        self.git = {}

    def programs(self):
        return self.tree.programs

    def pythons(self):
        return [("3.11", str(self.tree.python))]

    def links(self, pl):
        return self.tree.links

    def prefetch(self, pl):
        return None

    def git_last_commit(self, folder):
        return self.git.get(disk_tools.norm(folder), 0)

    def exe_info(self, path):
        return {"CompanyName": "Fake Co", "ProductName": "Mystery Tool", "FileDescription": "Mystery Tool"} \
            if "mystery" in str(path).lower() else {}

    def disk_usage(self, pl):
        return 1000 * 1024 ** 3, 900 * 1024 ** 3, 100 * 1024 ** 3


class Tree:
    """Builds the fake drive in a temporary folder. .places / .sources go to disk_tools.scan()."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="zyraena_disk_test_"))
        r = self.root
        self.home = r / "Users" / "me"
        local, roaming = self.home / "AppData" / "Local", self.home / "AppData" / "Roaming"
        docs = self.home / "Documents"
        projects = docs / "Projects"
        self.temp = local / "Temp"
        write(r / "Windows" / "System32" / "kernel.dll", 32 * KB)
        write(r / "pagefile.sys", 16 * KB)
        # a program with a registry entry, a system folder, an unknown product folder
        self.foo = r / "Program Files" / "Foo"
        write(self.foo / "foo.exe", 40 * KB)
        write(r / "Program Files" / "Common Files" / "shared.dll", 8 * KB)
        write(r / "Program Files" / "Mystery" / "mystery.exe", 24 * KB)
        # Steam: one installed game, one leftover folder without a manifest
        self.steam = r / "Program Files (x86)" / "Steam"
        apps = self.steam / "steamapps"
        write(apps / "appmanifest_123.acf", text='"AppState"\n{\n\t"appid"\t\t"123"\n\t"name"\t\t"Fake Game"\n'
                                                  '\t"installdir"\t\t"FakeGame"\n\t"SizeOnDisk"\t\t"1000"\n}\n')
        write(apps / "common" / "FakeGame" / "game.exe", 128 * KB)
        write(apps / "shadercache" / "123" / "s.bin", 8 * KB)
        write(apps / "common" / "OldGame" / "mods.zip", 48 * KB)
        write(self.steam / "steam.exe", 16 * KB)
        write(self.steam / "userdata" / "1" / "config" / "localconfig.vdf",
              text='"UserLocalConfigStore"\n{\n "Software"\n {\n  "Valve"\n  {\n   "Steam"\n   {\n    "apps"\n    {\n'
                   '     "123"\n     {\n      "LastPlayed"\t\t"1700000000"\n     }\n    }\n   }\n  }\n }\n}\n')
        # Python, venvs, caches
        self.python = local / "Programs" / "Python" / "Python311"
        write(self.python / "python.exe", 16 * KB)
        self.voice = local / "Zyraena" / "voice"
        self.egitim = projects / "Wichelberg" / "data" / "egitim" / "venv"
        make_venv(self.egitim, home=str(self.python), packages=("torch", "numpy"))
        self.voice_env = make_venv(self.voice / "env", home=str(self.python), packages=("faster-whisper",),
                                   pth=[str(self.egitim / "Lib" / "site-packages")])
        self.proj = projects / "proj1"
        self.proj_venv = make_venv(self.proj / ".venv", home=str(self.python), packages=("torch", "numpy"))
        self.twin_venv = make_venv(projects / "proj2" / "venv", home=str(self.python), packages=("torch", "numpy"))
        self.base_venv = make_venv(projects / "proj3" / ".venv", home=str(self.python), packages=("requests",))
        self.user_venv = make_venv(projects / "proj4" / ".venv", home=str(self.python), packages=("flask",),
                                   pth=[str(self.base_venv / "Lib" / "site-packages")])
        write(self.proj / "main.py", text='MODEL = "org/model"\nOTHER = "not/cached"\n')
        self.pip = local / "pip" / "cache"
        write(self.pip / "wheel.whl", 96 * KB)
        self.hub = self.home / ".cache" / "huggingface" / "hub"
        self.model = self.hub / "models--org--model"
        write(self.model / "blobs" / "weights", 80 * KB)
        write(self.temp / "old.tmp", 4 * KB)
        self.mei_old = self.temp / "_MEI111"
        write(self.mei_old / "base_library.zip", 32 * KB)
        self.mei_own = self.temp / "_MEI222"
        write(self.mei_own / "base_library.zip", 32 * KB)
        write(self.temp / "_MEI333" / "other.txt", 4 * KB)  # not PyInstaller's
        self.downloads = self.home / "Downloads"
        write(self.downloads / "movie.mkv", 72 * KB)
        self.failsafe = docs / "Failsafe"
        make_venv(self.failsafe / "backup" / ".venv", home=str(self.python))
        self.app = docs / "Apps" / "Zyraena"
        write(self.app / "Zyraena.exe", 24 * KB)
        # a hard link: the same wheel under the pip cache and inside proj1's venv
        os.link(self.pip / "wheel.whl", self.proj_venv / "Lib" / "site-packages" / "wheel_copy.whl")
        self.programs = [
            {"_key": "hklm64\\Foo", "DisplayName": "Foo", "Publisher": "Foo Inc", "InstallLocation": str(self.foo),
             "UninstallString": f'"{self.foo}\\unins000.exe"', "EstimatedSize": 10},
            {"_key": "hklm64\\Ghost", "DisplayName": "Ghost App", "Publisher": "Nobody",
             "UninstallString": "MsiExec.exe /X{GHOST}", "EstimatedSize": 2048},
            {"_key": "hklm64\\VC", "DisplayName": "Microsoft Visual C++ 2015 Redistributable (x64)",
             "Publisher": "Microsoft Corporation", "UninstallString": "x", "EstimatedSize": 20},
            {"_key": "hklm64\\Hidden", "DisplayName": "Hidden part", "SystemComponent": 1},
            {"_key": "hklm64\\Steam App 123", "DisplayName": "Fake Game"},
            {"_key": "hkcu\\Python", "DisplayName": "Python 3.11.9 (64-bit)", "Publisher": "Python Software Foundation",
             "UninstallString": '"C:\\py-setup.exe" /uninstall'},
        ]
        self.links = [
            {"source": "shortcut", "name": "Foo", "where": str(self.home / "Desktop" / "Foo.lnk"),
             "target": str(self.foo / "foo.exe")},
            {"source": "task", "name": "\\Hannah", "where": "Task Scheduler", "target": str(r / "gone" / "hannah.exe")},
        ]
        self.places = disk_tools.Places(
            drive=r, home=self.home, local=local, roaming=roaming, temp=self.temp, program_data=r / "ProgramData",
            program_files=[r / "Program Files", r / "Program Files (x86)"], windows=r / "Windows", documents=docs,
            project_roots=[projects, docs / "Work"], voice_home=self.voice, failsafe=self.failsafe,
            egitim_venv=self.egitim, wichelberg_app=docs / "Apps" / "Wichelberg" / "_wichelberg",
            zyraena_app=self.app, zyraena_source=None, own_meipass=str(self.mei_own), steam=self.steam,
            hf_hub=self.hub, torch_home=self.home / ".cache" / "torch", prefetch=None)
        self.sources = FakeSources(self)

    def scan(self, **kw):
        old = disk_tools.MIN_FOLDER_BYTES
        disk_tools.MIN_FOLDER_BYTES = 0  # the fake folders are tiny
        try:
            return disk_tools.scan(self.places, self.sources, "tr", **kw)
        finally:
            disk_tools.MIN_FOLDER_BYTES = old

    def age(self, path, seconds):
        t = time.time() - seconds
        os.utime(path, (t, t))

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def by_path(scan, path):
    return next((it for it in scan.items if it.path and disk_tools.norm(it.path) == disk_tools.norm(path)), None)
