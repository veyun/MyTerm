#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
#
#############################################################################
##
## Copyright (c) 2013-2020, gamesun
## All right reserved.
##
## This file is part of MyTerm.
##
## MyTerm is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## MyTerm is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with MyTerm.  If not, see <http://www.gnu.org/licenses/>.
##
#############################################################################


# PySide
#from PySide import QtCore, QtGui
#from PySide.QtCore import Signal
#base = QtGui.QComboBox
#signal = Signal

# PySide2
#from PySide2 import QtCore, QtWidgets
#from PySide2.QtCore import Signal
#base = QtWidgets.QComboBox
#signal = Signal

# PyQt5
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import pyqtSignal
base = QtWidgets.QComboBox
signal = pyqtSignal

class Combo(base):
    listShowEntered = signal()
    
    def __init__(self, *args, **kwargs):
        super(Combo, self).__init__(*args, **kwargs)

    def mousePressEvent(self, event):
        self.listShowEntered.emit()
        super(Combo, self).mousePressEvent(event)

    def setCurrentText(self, text):
        self.setEditText(text)
