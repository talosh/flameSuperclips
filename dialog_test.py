import os
import sys
import sgtk
from PySide2 import QtWidgets, QtCore

class Dialog(QtWidgets.QDialog):
    def __init__(self):
        super(Dialog, self).__init__()
        self.formGroupBox = QGroupBox("Form layout")


print ('***** hello from dialog test')
print ("Qt version: " + str(QtCore.qVersion()))
prefs_dialog = Dialog()
prefs_dialog.exec_()
