from __future__ import annotations

import os
import sys


def main() -> int:
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        print("缺少 PySide6，请先运行：pip install -r requirements.txt")
        return 1

    from classroom_hand_raise.shared.single_instance import SingleInstanceLock
    from classroom_hand_raise.student.ui import StudentWindow

    app = QApplication(sys.argv)
    lock = SingleInstanceLock("student", "学生端已经在运行，请不要重复打开。")
    if not lock.try_acquire():
        if smoke_test:
            print(lock.message)
            app.quit()
            return 2
        QMessageBox.warning(None, "提示", lock.message)
        app.quit()
        return 0

    app.aboutToQuit.connect(lock.release)
    try:
        window = StudentWindow()
        if smoke_test:
            print(window.windowTitle())
            window.force_exit = True
            window.close()
            app.quit()
            return 0

        window.center_on_screen()
        window.show()
        return app.exec()
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
