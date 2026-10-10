import sys, os
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow(os.path.join(os.path.expanduser("~"), ".macrostudio", "macros.json"))
    w.show(); sys.exit(app.exec())
