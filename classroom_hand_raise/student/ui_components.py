from __future__ import annotations


def apply_student_style(widget) -> None:
    widget.setStyleSheet(
        """
        QMainWindow, QWidget {
            background: #f7f8fb;
            color: #1f2937;
            font-family: "Microsoft YaHei", "Segoe UI";
            font-size: 14px;
        }
        QFrame#TopBar, QGroupBox {
            background: #ffffff;
            border: 1px solid #d8dee9;
            border-radius: 8px;
        }
        QGroupBox {
            margin-top: 14px;
            font-weight: 700;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        QLabel[class="title"] {
            font-size: 20px;
            font-weight: 700;
        }
        QLabel[class="status"] {
            color: #475569;
            font-weight: 600;
        }
        QPushButton {
            background: #2563eb;
            color: white;
            border: 0;
            border-radius: 8px;
            padding: 9px 14px;
            font-weight: 700;
        }
        QPushButton#MainAction {
            font-size: 18px;
            padding: 18px 16px;
        }
        QPushButton#SecondaryButton {
            background: #475569;
        }
        QPushButton#FeedbackButton {
            background: #0f766e;
        }
        QPushButton:disabled {
            background: #cbd5e1;
            color: #64748b;
        }
        QLineEdit, QTextEdit, QComboBox {
            background: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 7px;
        }
        """
    )
