"""
CCUT Folder Selector
폴더 선택 다이얼로그를 열어 사용자가 CCUT 프로젝트 폴더를 선택할 수 있게 합니다.
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog


def select_folder(initial_dir=None):
    """폴더 선택 다이얼로그를 열고 선택된 경로를 반환합니다."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    folder_path = filedialog.askdirectory(
        title="CCUT 폴더를 선택하세요",
        initialdir=initial_dir or os.path.expanduser("~"),
    )

    root.destroy()
    return folder_path


def validate_ccut_folder(path):
    """선택된 폴더가 유효한 CCUT 프로젝트 폴더인지 확인합니다."""
    expected_dirs = ["ccut_core", "ccut_ui", "ui"]
    found = [d for d in expected_dirs if os.path.isdir(os.path.join(path, d))]
    return len(found) >= 2


def main():
    initial_dir = sys.argv[1] if len(sys.argv) > 1 else None
    folder = select_folder(initial_dir)

    if not folder:
        print("폴더가 선택되지 않았습니다.")
        sys.exit(1)

    print(f"선택된 폴더: {folder}")

    if validate_ccut_folder(folder):
        print("유효한 CCUT 프로젝트 폴더입니다.")
    else:
        print("경고: CCUT 프로젝트 폴더가 아닐 수 있습니다.")
        print("  (ccut_core, ccut_ui, ui 디렉토리가 필요합니다)")

    # 선택된 경로를 파일에 저장 (다른 모듈에서 사용 가능)
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ccut_path")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(folder)
    print(f"경로가 저장되었습니다: {config_path}")

    return folder


if __name__ == "__main__":
    main()
