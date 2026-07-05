# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Installs VredX into the VRED Scripts folder.

Usage (regular Python, not inside VRED):

    python install.py                     # auto-detect newest VREDPro Scripts dir
    python install.py <Scripts dir>       # explicit target folder

VRED loads script plugins from the installation directory, e.g.
C:\\Program Files\\Autodesk\\VREDPro-19.1\\lib\\plugins\\WIN64\\Scripts
(writing there may require an elevated/administrator prompt).
"""

import os
import re
import shutil
import sys
import zipfile

PLUGIN_NAME = "VredX"
ROOT = os.path.dirname(os.path.abspath(__file__))
ZIPPED_PACKAGE = "vredx"


def find_scripts_dir():
    autodesk = r"C:\Program Files\Autodesk"
    if not os.path.isdir(autodesk):
        return None

    def version_key(name):
        match = re.match(r"VREDPro-(\d+)\.(\d+)", name)
        return (int(match.group(1)), int(match.group(2))) if match else (0, 0)

    candidates = [d for d in os.listdir(autodesk)
                  if re.match(r"VREDPro-\d+\.\d+$", d)
                  and os.path.isdir(os.path.join(autodesk, d, "lib", "plugins",
                                                 "WIN64", "Scripts"))]
    if not candidates:
        return None

    newest = max(candidates, key=version_key)
    return os.path.join(autodesk, newest, "lib", "plugins", "WIN64", "Scripts")


def zip_package(package_dir, zip_path):
    """Zip a Python package so it is importable via sys.path."""
    package_name = os.path.basename(package_dir)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for dirpath, dirnames, filenames in os.walk(package_dir):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for filename in filenames:
                if filename.endswith(".pyc"):
                    continue
                full = os.path.join(dirpath, filename)
                arcname = os.path.join(
                    package_name, os.path.relpath(full, package_dir))
                archive.write(full, arcname)


def install_plugin(scripts_dir):
    source = ROOT
    target = os.path.join(scripts_dir, PLUGIN_NAME)
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(source, target,
                        ignore=shutil.ignore_patterns(
                            "__pycache__", "*.pyc", "tests",
                            ".pytest_cache", "docs", "install.py",
                            ".git", ".gitignore", "CHANGELOG.md",
                            "resources/libraries"))
        package_dir = os.path.join(target, ZIPPED_PACKAGE)
        if not os.path.isfile(os.path.join(package_dir, "__init__.py")):
            shutil.rmtree(target, ignore_errors=True)
            sys.exit("VredX is missing its Python package: expected\n"
                     "  %s\\__init__.py\n"
                     "The source checkout is incomplete; aborting "
                     "(nothing installed)." % package_dir)
        zip_package(package_dir, package_dir + ".zip")
        shutil.rmtree(package_dir)
        print("  packaged %s/ -> %s.zip (keeps VRED's plugin "
              "scanner out of the library modules)"
              % (ZIPPED_PACKAGE, ZIPPED_PACKAGE))
    except PermissionError:
        sys.exit("Permission denied writing to:\n  %s\n"
                 "Run this script from an elevated (administrator) prompt."
                 % target)
    print("Installed %s to:\n  %s" % (PLUGIN_NAME, target))


def main():
    scripts_dir = sys.argv[1] if len(sys.argv) > 1 else find_scripts_dir()
    if scripts_dir is None:
        sys.exit("Could not find a VREDPro installation under "
                 "C:\\Program Files\\Autodesk. Pass the Scripts path "
                 "explicitly:\n    python install.py <path-to-Scripts>")
    install_plugin(scripts_dir)
    print("Restart VRED (or reload script plugins) to load VredX.")


if __name__ == "__main__":
    main()
