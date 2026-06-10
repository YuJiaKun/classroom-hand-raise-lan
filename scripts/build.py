from __future__ import annotations

import argparse
from pathlib import Path
import sys


TARGETS = {
    "teacher": {
        "name": "教师端",
        "entry": "classroom_hand_raise/teacher/app.py",
        "workpath": "build/teacher",
    },
    "student": {
        "name": "学生端",
        "entry": "classroom_hand_raise/student/app.py",
        "workpath": "build/student",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build classroom desktop executables.")
    parser.add_argument("target", choices=sorted(TARGETS))
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    target = TARGETS[args.target]

    try:
        import PyInstaller.__main__
    except ImportError:
        print("缺少 PyInstaller，请先运行：python -m pip install -r requirements.txt")
        return 1

    PyInstaller.__main__.run(
        [
            "--noconfirm",
            "--clean",
            "--windowed",
            "--name",
            target["name"],
            "--distpath",
            str(project_root / "dist"),
            "--workpath",
            str(project_root / target["workpath"]),
            "--specpath",
            str(project_root / "build" / "specs"),
            str(project_root / target["entry"]),
        ]
    )
    print(f"{target['name']} 已输出到 dist/{target['name']}/{target['name']}.exe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
