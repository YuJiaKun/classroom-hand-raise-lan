from __future__ import annotations

from PySide6.QtWidgets import QLabel


def metric_label(title: str, value: str = "0") -> QLabel:
    label = QLabel(f"{title}：{value}")
    label.setProperty("class", "metric")
    return label


def apply_teacher_style(widget) -> None:
    widget.setStyleSheet(
        """
        QMainWindow, QWidget {
            background: #f5f7fb;
            color: #1f2937;
            font-family: "Microsoft YaHei", "Segoe UI";
            font-size: 13px;
        }
        QFrame#TopBar {
            background: #ffffff;
            border: 1px solid #d8dee9;
            border-radius: 8px;
        }
        QLabel[class="title"] {
            font-size: 20px;
            font-weight: 700;
        }
        QLabel[class="metric"] {
            background: #eef4ff;
            border: 1px solid #c8dcff;
            border-radius: 6px;
            padding: 6px 10px;
            font-weight: 600;
        }
        QLabel[class="alert"] {
            background: #fff7ed;
            border: 1px solid #fed7aa;
            border-radius: 6px;
            color: #9a3412;
            padding: 8px 10px;
            font-weight: 700;
        }
        QGroupBox {
            background: #ffffff;
            border: 1px solid #d8dee9;
            border-radius: 8px;
            margin-top: 14px;
            font-weight: 700;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        QPushButton {
            background: #2563eb;
            color: white;
            border: 0;
            border-radius: 6px;
            padding: 7px 12px;
            font-weight: 600;
        }
        QPushButton:disabled {
            background: #cbd5e1;
            color: #64748b;
        }
        QPushButton#SecondaryButton {
            background: #475569;
        }
        QTableWidget, QListWidget {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            gridline-color: #e5e7eb;
        }
        QHeaderView::section {
            background: #f1f5f9;
            color: #334155;
            border: 0;
            padding: 6px;
            font-weight: 700;
        }
        QComboBox {
            background: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 6px;
        }
        """
    )
