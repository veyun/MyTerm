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


import sys, os
import datetime
import pickle
import csv
from lxml import etree as ET
import defusedxml.cElementTree as safeET
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox, QWidget, \
    QTableWidgetItem, QPushButton, QActionGroup, QDesktopWidget, QToolButton, \
    QFileDialog
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSignalMapper, QFile, QIODevice, \
    QPoint, QPropertyAnimation
from PyQt5.QtGui import QFontMetrics
from combo import Combo
import sip
import appInfo
from configpath import get_config_path
from ui.ui_mainwindow import Ui_MainWindow
from res import resources_pyqt5
import serial
from serial.tools.list_ports import comports
from time import sleep

extension = os.path.splitext(sys.argv[0])[1]
if extension != '.py':
    import except_logger
    sys.excepthook = except_logger.exceptHook

if os.name == 'nt':
    EDITOR_FONT = "Consolas"
    UI_FONT = "Meiryo UI"
elif os.name == 'posix':
    EDITOR_FONT = "Monospace"
    UI_FONT = None

VIEWMODE_ASCII           = 0
VIEWMODE_HEX_LOWERCASE   = 1
VIEWMODE_HEX_UPPERCASE   = 2

class MainWindow(QMainWindow, Ui_MainWindow):
    """docstring for MainWindow."""
    def __init__(self, parent=None):
        super(MainWindow, self).__init__()
        self._csvFilePath = ""
        self.serialport = serial.Serial()
        self.readerThread = ReaderThread(self)
        self.readerThread.setPort(self.serialport)
        self.portMonitorThread = PortMonitorThread(self)
        self.portMonitorThread.setPort(self.serialport)
        self.periodThread = PeriodThread(self)
        self._localEcho = None
        self._viewMode = None
        self._quickSendOptRow = 1
        self._is_periodic_send = False

        self.setupUi(self)
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        font = QtGui.QFont()
        font.setFamily(EDITOR_FONT)
        font.setPointSize(9)
        self.txtEdtOutput.setFont(font)
        self.txtEdtInput.setFont(font)
        #self.quickSendTable.setFont(font)
        self.setupMenu()
        self.setupFlatUi()
        
        icon = QtGui.QIcon(":/MyTerm.ico")
        self.setWindowIcon(icon)
        self.actionAbout.setIcon(icon)

        self.defaultStyleWidget = QWidget()
        self.defaultStyleWidget.setWindowIcon(icon)

        icon = QtGui.QIcon(":/qt_logo_16.ico")
        self.actionAbout_Qt.setIcon(icon)

        self._viewGroup = QActionGroup(self)
        self._viewGroup.addAction(self.actionAscii)
        self._viewGroup.addAction(self.actionHex_lowercase)
        self._viewGroup.addAction(self.actionHEX_UPPERCASE)
        self._viewGroup.setExclusive(True)

        # bind events
        self.actionOpen_Cmd_File.triggered.connect(self.openQuickSend)
        self.actionSave_Log.triggered.connect(self.onSaveLog)
        self.actionExit.triggered.connect(self.onExit)

        self.actionOpen.triggered.connect(self.openPort)
        self.actionClose.triggered.connect(self.closePort)

        #self.actionPort_Config_Panel.triggered.connect(self.onTogglePrtCfgPnl)
        self.actionQuick_Send_Panel.triggered.connect(self.onToggleQckSndPnl)
        self.actionSend_Hex_Panel.triggered.connect(self.onToggleHexPnl)
        #self.dockWidget_PortConfig.visibilityChanged.connect(self.onVisiblePrtCfgPnl)
        self.dockWidget_QuickSend.visibilityChanged.connect(self.onVisibleQckSndPnl)
        self.dockWidget_SendHex.visibilityChanged.connect(self.onVisibleHexPnl)
        self.actionLocal_Echo.triggered.connect(self.onLocalEcho)
        self.actionAlways_On_Top.triggered.connect(self.onAlwaysOnTop)

        self.actionAscii.triggered.connect(self.onViewChanged)
        self.actionHex_lowercase.triggered.connect(self.onViewChanged)
        self.actionHEX_UPPERCASE.triggered.connect(self.onViewChanged)

        self.actionAbout.triggered.connect(self.onAbout)
        self.actionAbout_Qt.triggered.connect(self.onAboutQt)

        self.cmbBaudRate.currentTextChanged.connect(self.onBaudRateChanged)
        self.cmbDataBits.currentTextChanged.connect(self.onDataBitsChanged)
        self.cmbStopBits.currentTextChanged.connect(self.onStopBitsChanged)
        self.cmbParity.currentTextChanged.connect(self.onParityChanged)
        self.chkRTSCTS.stateChanged.connect(self.onRTSCTSChanged)
        self.chkXonXoff.stateChanged.connect(self.onXonXoffChanged)
        
        self.btnOpen.clicked.connect(self.onOpen)
        self.btnClear.clicked.connect(self.onClear)
        self.btnSaveLog.clicked.connect(self.onSaveLog)
        #self.btnEnumPorts.clicked.connect(self.onEnumPorts)
        self.btnSendHex.clicked.connect(self.onSend)
        
        self.btnPeriodicSend.clicked.connect(self.onPeriodicSend)
        self.periodThread.trigger.connect(self.onPeriodTrigger)

        self.readerThread.read.connect(self.onReceive)
        self.readerThread.exception.connect(self.onReaderExcept)
        self._signalMapQuickSendOpt = QSignalMapper(self)
        self._signalMapQuickSendOpt.mapped[int].connect(self.onQuickSendOptions)
        self._signalMapQuickSend = QSignalMapper(self)
        self._signalMapQuickSend.mapped[int].connect(self.onQuickSend)

        # initial action
        self.setTabWidth(4)
        self.actionHEX_UPPERCASE.setChecked(True)
        self.readerThread.setViewMode(VIEWMODE_HEX_UPPERCASE)
        self.initQuickSend()
        self.restoreLayout()
        self.moveScreenCenter()
        self.syncMenu()
        self.setPortCfgBarVisible(False)

        if self.isMaximized():
            self.setMaximizeButton("restore")
        else:
            self.setMaximizeButton("maximize")

        self.loadSettings()
        self.onEnumPorts()

    def setTabWidth(self, n):
        fm = QFontMetrics(self.txtEdtOutput.fontMetrics())
        if hasattr(fm, 'horizontalAdvance'):
            w = fm.horizontalAdvance(' ')
        else:
            w = fm.width(' ')
        self.txtEdtOutput.setTabStopWidth(n * w)
        
        fm = QFontMetrics(self.txtEdtInput.fontMetrics())
        if hasattr(fm, 'horizontalAdvance'):
            w = fm.horizontalAdvance(' ')
        else:
            w = fm.width(' ')
        self.txtEdtInput.setTabStopWidth(n * w)

    def onBaudRateChanged(self, text):
        self.serialport.baudrate = self.cmbBaudRate.currentText()
        
    def onDataBitsChanged(self, text):
        self.serialport.bytesize = self.getDataBits()
        
    def onStopBitsChanged(self, text):
        old = self.serialport.stopbits
        try:
            self.serialport.stopbits = self.getStopBits()
        except ValueError:
            QMessageBox.critical(self.defaultStyleWidget, "Exception", "Wrong setting", QMessageBox.Close)
            self.cmbStopBits.setCurrentText('1')
        except Exception as e:
            QMessageBox.critical(self.defaultStyleWidget, "Exception", str(e), QMessageBox.Close)
            self.cmbStopBits.setCurrentText('1')
    
    def onParityChanged(self, text):
        self.serialport.parity = self.getParity()
        
    def onRTSCTSChanged(self, state):
        self.serialport.rtscts = self.chkRTSCTS.isChecked()
        
    def onXonXoffChanged(self, state):
        self.serialport.xonxoff = self.chkXonXoff.isChecked()

    def setupMenu(self):
        self.menuMenu = QtWidgets.QMenu()
        self.menuMenu.setTitle("&File")
        self.menuMenu.setObjectName("menuMenu")
        self.menuView = QtWidgets.QMenu(self.menuMenu)
        self.menuView.setTitle("&View")
        self.menuView.setObjectName("menuView")

        self.menuView.addAction(self.actionAscii)
        self.menuView.addAction(self.actionHex_lowercase)
        self.menuView.addAction(self.actionHEX_UPPERCASE)
        self.menuMenu.addAction(self.actionOpen_Cmd_File)
        self.menuMenu.addAction(self.actionSave_Log)
        self.menuMenu.addSeparator()
        #self.menuMenu.addAction(self.actionPort_Config_Panel)
        self.menuMenu.addAction(self.actionQuick_Send_Panel)
        self.menuMenu.addAction(self.actionSend_Hex_Panel)
        self.menuMenu.addAction(self.menuView.menuAction())
        self.menuMenu.addAction(self.actionLocal_Echo)
        self.menuMenu.addAction(self.actionAlways_On_Top)
        self.menuMenu.addSeparator()
        self.menuMenu.addAction(self.actionAbout)
        self.menuMenu.addAction(self.actionAbout_Qt)
        self.menuMenu.addSeparator()
        self.menuMenu.addAction(self.actionExit)

        self.sendOptMenu = QtWidgets.QMenu()
        self.actionSend_Hex = QtWidgets.QAction(self)
        self.actionSend_Hex.setText("HEX")
        self.actionSend_Hex.setStatusTip("Send Hex (e.g. 31 32 FF)")

        self.actionSend_Asc = QtWidgets.QAction(self)
        self.actionSend_Asc.setText("ASCII")
        self.actionSend_Asc.setStatusTip("Send Asc (e.g. abc123)")
        
        self.actionSend_AscS = QtWidgets.QAction(self)
        self.actionSend_AscS.setText(r"ASCII Special chars(\n \r \t...)")
        self.actionSend_AscS.setStatusTip("Send Asc (e.g. abc123) converting escape chars")

        self.actionSend_HF = QtWidgets.QAction(self)
        self.actionSend_HF.setText("HEX text File")
        self.actionSend_HF.setStatusTip('Send text file in HEX form(e.g. "31 32 FF")')

        self.actionSend_AF = QtWidgets.QAction(self)
        self.actionSend_AF.setText("ASCII text file")
        self.actionSend_AF.setStatusTip('Send text file in ASCII form(e.g. "abc123")')

        self.actionSend_BF = QtWidgets.QAction(self)
        self.actionSend_BF.setText("Bin/HEX file")
        self.actionSend_BF.setStatusTip("Send a Bin/HEX file")

        self.sendOptMenu.addAction(self.actionSend_Hex)
        self.sendOptMenu.addAction(self.actionSend_Asc)
        self.sendOptMenu.addAction(self.actionSend_AscS)
        self.sendOptMenu.addAction(self.actionSend_HF)
        self.sendOptMenu.addAction(self.actionSend_AF)
        self.sendOptMenu.addAction(self.actionSend_BF)

        self.actionSend_Hex.triggered.connect(self.onSetSendHex)
        self.actionSend_Asc.triggered.connect(self.onSetSendAsc)
        self.actionSend_AscS.triggered.connect(self.onSetSendAscS)
        self.actionSend_HF.triggered.connect(self.onSetSendHF)
        self.actionSend_AF.triggered.connect(self.onSetSendAF)
        self.actionSend_BF.triggered.connect(self.onSetSendBF)

    def setupFlatUi(self):
        self._dragPos = self.pos()
        self._isDragging = False
        self.setMouseTracking(True)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("""
            QWidget {
                background-color: %(BackgroundColor)s;
                /*background-image: url(:/background.png);*/
                outline: none;
            }
            QToolBar {
                border: none;
            }
            QLabel {
                color:%(TextColor)s;
                font-size:9pt;
                font-family:%(UIFont)s;
            }
            
            QComboBox {
                color:%(TextColor)s;
                font-size:9pt;
                font-family:%(UIFont)s;
            }
            QComboBox {
                border: none;
                padding: 1px 1px 1px 3px;
            }
            QComboBox:editable {
                background: white;
            }
            QComboBox:!editable, QComboBox::drop-down:editable { background: #62c7e0; }
            QComboBox:!editable:hover, QComboBox::drop-down:editable:hover { background: #c7eaf3; }
            QComboBox:!editable:pressed, QComboBox::drop-down:editable:pressed { background: #35b6d7; }
            QComboBox:on {
                padding-top: 3px;
                padding-left: 4px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 16px;
                border: none;
            }
            QComboBox::down-arrow { image: url(:/downarrow.png); }
            QComboBox::down-arrow:on { image: url(:/uparrow.png); }
            QAbstractItemView { background: white; }

            QSpinBox {
                border: none;
                background: white;
                color:%(TextColor)s;
                font-size:9pt;
                font-family:%(UIFont)s;
            }
            QSpinBox::up-button { image: url(:/uparrow.png); height: 12px; }
            QSpinBox::down-button { image: url(:/downarrow.png); height: 12px; }
            QSpinBox::up-button, QSpinBox::down-button { background: #62c7e0; }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #c7eaf3; }
            QSpinBox::up-button:pressed, QSpinBox::down-button:pressed { background: #35b6d7; }
            
            QGroupBox {
                color:%(TextColor)s;
                font-size:8pt;
                font-family:%(UIFont)s;
                border: 1px solid gray;
                margin-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left:5px;
                top:3px;
            }
            
            QCheckBox {
                color:%(TextColor)s;
                spacing: 5px;
                font-size:9pt;
                font-family:%(UIFont)s;
            }
            QCheckBox::indicator:unchecked { image: url(:/checkbox_unchecked.png); }
            QCheckBox::indicator:unchecked:hover { image: url(:/checkbox_unchecked_hover.png); }
            QCheckBox::indicator:unchecked:pressed { image: url(:/checkbox_unchecked_pressed.png); }
            QCheckBox::indicator:checked { image: url(:/checkbox_checked.png); }
            QCheckBox::indicator:checked:hover { image: url(:/checkbox_checked_hover.png); }
            QCheckBox::indicator:checked:pressed { image: url(:/checkbox_checked_pressed.png); }
            
            QScrollBar:horizontal {
                background-color:%(BackgroundColor)s;
                border: none;
                height: 15px;
                margin: 0px 20px 0 20px;
            }
            QScrollBar::handle:horizontal {
                background: %(ScrollBar_Handle)s;
                min-width: 20px;
            }
            QScrollBar::add-line:horizontal {
                image: url(:/rightarrow.png);
                border: none;
                background: %(ScrollBar_Line)s;
                width: 20px;
                subcontrol-position: right;
                subcontrol-origin: margin;
            }
            QScrollBar::sub-line:horizontal {
                image: url(:/leftarrow.png);
                border: none;
                background: %(ScrollBar_Line)s;
                width: 20px;
                subcontrol-position: left;
                subcontrol-origin: margin;
            }
            
            QScrollBar:vertical {
                background-color:%(BackgroundColor)s;
                border: none;
                width: 15px;
                margin: 20px 0px 20px 0px;
            }
            QScrollBar::handle::vertical {
                background: %(ScrollBar_Handle)s;
                min-height: 20px;
            }
            QScrollBar::add-line::vertical {
                image: url(:/downarrow.png);
                border: none;
                background: %(ScrollBar_Line)s;
                height: 20px;
                subcontrol-position: bottom;
                subcontrol-origin: margin;
            }
            QScrollBar::sub-line::vertical {
                image: url(:/uparrow.png);
                border: none;
                background: %(ScrollBar_Line)s;
                height: 20px;
                subcontrol-position: top;
                subcontrol-origin: margin;
            }
            
            QTableView {
                background-color: white;
                /*selection-background-color: #FF92BB;*/
                border: 1px solid %(TableView_Border)s;
                color: %(TextColor)s;
            }
            QTableView::focus {
                /*border: 1px solid #2a7fff;*/
            }
            QTableView QTableCornerButton::section {
                border: none;
                border-right: 1px solid %(TableView_Border)s;
                border-bottom: 1px solid %(TableView_Border)s;
                background-color: %(TableView_Corner)s;
            }
            QTableView QWidget {
                background-color: white;
            }
            QTableView::item:focus {
                border: 1px red;
                background-color: transparent;
                color: %(TextColor)s;
            }
            QHeaderView::section {
                border: none;
                border-right: 1px solid %(TableView_Border)s;
                border-bottom: 1px solid %(TableView_Border)s;
                padding-left: 2px;
                padding-right: 2px;
                color: #444444;
                background-color: %(TableView_Header)s;
            }
            QTextEdit {
                background-color:white;
                color:%(TextColor)s;
                border-top: none;
                border-bottom: none;
                border-left: 2px solid %(BackgroundColor)s;
                border-right: 2px solid %(BackgroundColor)s;
            }
            QTextEdit::focus {
            }
            
            QToolButton, QPushButton {
                background-color:#30a7b8;
                border:none;
                color:#ffffff;
                font-size:9pt;
                font-family:%(UIFont)s;
            }
            QToolButton:hover, QPushButton:hover {
                background-color:#51c0d1;
            }
            QToolButton:pressed, QPushButton:pressed {
                background-color:#3a9ecc;
            }
            
            QMenuBar {
                color: %(TextColor)s;
                height: 24px;
            }
            QMenuBar::item {
                background-color: transparent;
                margin: 8px 0px 0px 0px;
                padding: 1px 8px 1px 8px;
                height: 15px;
            }
            QMenuBar::item:selected {
                background: #51c0d1;
            }
            QMenuBar::item:pressed {
                
            }
            /*
            QMenu {
                color: %(TextColor)s;
                background: #ffffff;
            }
            QMenu {
                margin: 2px;
            }
            QMenu::item {
                padding: 2px 25px 2px 21px;
                border: 1px solid transparent;
            }
            QMenu::item:selected {
                background: #51c0d1;
            }
            QMenu::icon {
                background: transparent;
                border: 2px inset transparent;
            }*/

            QDockWidget {
                font-size:9pt;
                font-family:%(UIFont)s;
                color: %(TextColor)s;
                titlebar-close-icon: none;
                titlebar-normal-icon: none;
            }
            QDockWidget::title {
                margin: 0;
                padding: 2px;
                subcontrol-origin: content;
                subcontrol-position: right top;
                text-align: left;
                background: #67baed;
                
            }
            QDockWidget::float-button {
                max-width: 12px;
                max-height: 12px;
                background-color:transparent;
                border:none;
                image: url(:/restore_inactive.png);
            }
            QDockWidget::float-button:hover {
                background-color:#227582;
                image: url(:/restore_active.png);
            }
            QDockWidget::float-button:pressed {
                padding: 0;
                background-color:#14464e;
                image: url(:/restore_active.png);
            }
            QDockWidget::close-button {
                max-width: 12px;
                max-height: 12px;
                background-color:transparent;
                border:none;
                image: url(:/close_inactive.png);
            }
            QDockWidget::close-button:hover {
                background-color:#ea5e00;
                image: url(:/close_active.png);
            }
            QDockWidget::close-button:pressed {
                background-color:#994005;
                image: url(:/close_active.png);
                padding: 0;
            }
            
        """ % dict(
            BackgroundColor =  '#99d9ea',
            TextColor =        '#202020',
            ScrollBar_Handle = '#61b9e1',
            ScrollBar_Line =   '#7ecfe4',
            TableView_Corner = '#8ae6d2',
            TableView_Header = '#8ae6d2',
            TableView_Border = '#eeeeee',
            UIFont = 'Microsoft YaHei UI',
        ))
        self.dockWidget_QuickSend.setStyleSheet("""
            QToolButton, QPushButton {
                background-color:#27b798;
                font-family:Tahoma;
                font-size:8pt;
                /*min-width:46px;*/
            }
            QToolButton:hover, QPushButton:hover {
                background-color:#3bd5b4;
            }
            QToolButton:pressed, QPushButton:pressed {
                background-color:#1d8770;
            }
        """)
        self.dockWidgetContents_2.setStyleSheet("""
            QPushButton {
                min-height:23px;
                min-width:50px;
            }
        """)

        w = self.frameGeometry().width()
        self._minBtn = QPushButton(self)
        self._minBtn.setGeometry(w-112,0,31,31)
        self._minBtn.clicked.connect(self.onMinimize)
        self._minBtn.setStyleSheet("""
            QPushButton {
                background-color:transparent;
                border:none;
                outline: none;
                image: url(:/minimize_inactive.png);
            }
            QPushButton:hover {
                background-color:#227582;
                image: url(:/minimize_active.png);
            }
            QPushButton:pressed {
                background-color:#14464e;
                image: url(:/minimize_active.png);
            }
        """)
        
        self._maxBtn = QPushButton(self)
        self._maxBtn.setGeometry(w-81,0,31,31)
        self._maxBtn.clicked.connect(self.onMaximize)
        self.setMaximizeButton("maximize")
        
        self._closeBtn = QPushButton(self)
        self._closeBtn.setGeometry(w-50,0,40,31)
        self._closeBtn.clicked.connect(self.onExit)
        self._closeBtn.setStyleSheet("""
            QPushButton {
                background-color:transparent;
                border:none;
                outline: none;
                image: url(:/close_inactive.png);
            }
            QPushButton:hover {
                background-color:#ea5e00;
                image: url(:/close_active.png);
            }
            QPushButton:pressed {
                background-color:#994005;
                image: url(:/close_active.png);
            }
        """)
        
        #self.toolBar.setFixedHeight(28)
        
        font = QtGui.QFont()
        font.setFamily(UI_FONT)
        font.setPointSize(9)
        
        x,y,w,h = 6,4,100,23
        self.btnMenu = QtWidgets.QToolButton(self)
        self.btnMenu.setFont(font)
        self.btnMenu.setEnabled(True)
        self.btnMenu.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.btnMenu.setIcon(QtGui.QIcon(':/MyTerm.ico'))
        self.btnMenu.setText('MyTerm  ')
        self.btnMenu.setGeometry(x,y,w,h)
        self.btnMenu.setMenu(self.menuMenu)
        self.btnMenu.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        
        #x,w = x+w+15,23
        #self.btnRefresh = QtWidgets.QToolButton(self)
        #self.btnRefresh.setEnabled(True)
        #self.btnRefresh.setIcon(QtGui.QIcon(':/refresh.ico'))
        #self.btnRefresh.setGeometry(x,y,w,h)
        #self.btnRefresh.setStyleSheet("""
            #QToolButton {
                #background-color:#6eccda;
            #}
            #QToolButton:hover {
                #background-color:#51c0d1;
            #}
            #QToolButton:pressed {
                #background-color:#3a9ecc;
            #}
        #""")
        #self.btnRefresh.clicked.connect(self.onEnumPorts)
        
        #self.verticalLayout_1.removeWidget(self.cmbPort)
        self.cmbPort = Combo(self.toolBar)
        self.cmbPort.setEditable(True)
        self.cmbPort.setCurrentText("")
        self.cmbPort.setParent(self)
        if os.name == 'nt':
            x,w = x+w+15,90
            self.cmbPort.setGeometry(x,y,w,h)
        elif os.name == 'posix':
            x,w = x+w+15,120
            self.cmbPort.setGeometry(x,y,w,h)
        self.cmbPort.listShowEntered.connect(self.onEnumPorts)
        self.cmbPort.currentTextChanged.connect(self.onPortChanged)
    
        self.btnOpen = QtWidgets.QToolButton(self.toolBar)
        self.btnOpen.setEnabled(True)
        self.btnOpen.setText("Open")
        #self.verticalLayout_1.removeWidget(self.btnOpen)
        self.btnOpen.setParent(self)
        x,w = x+w+15,60
        self.btnOpen.setGeometry(x,y,w,h)
        
        self.btnClear = QtWidgets.QToolButton(self.toolBar)
        self.btnClear.setEnabled(True)
        self.btnClear.setText("Clear")
        #self.verticalLayout_1.removeWidget(self.btnClear)
        self.btnClear.setParent(self)
        x,w = x+w+15,60
        self.btnClear.setGeometry(x,y,w,h)

        self.btnSaveLog = QtWidgets.QToolButton(self.toolBar)
        self.btnSaveLog.setEnabled(True)
        self.btnSaveLog.setText("Save Log")
        #self.verticalLayout_1.removeWidget(self.btnSaveLog)
        self.btnSaveLog.setParent(self)
        x,w = x+w+15,80
        self.btnSaveLog.setGeometry(x,y,w,h)

        self.btnTogglePortCfgBar = QtWidgets.QToolButton(self.toolBar)
        self.btnTogglePortCfgBar.setEnabled(True)
        #self.btnTogglePortCfgBar.setIcon(QtGui.QIcon(':/up.png'))
        self.btnTogglePortCfgBar.setStyleSheet("QToolButton {image: url(:/up.png);}")
        self.btnTogglePortCfgBar.setParent(self)
        x,w = x+w+15,23
        self.btnTogglePortCfgBar.setGeometry(x,y,w,h)
        self.btnTogglePortCfgBar.clicked.connect(self.onTogglePortCfgBar)
        
        #self.pos_animation = QPropertyAnimation()
        #self.pos_animation.setTargetObject(self.frame_PortCfg)
        #self.pos_animation.setPropertyName("pos".encode())
        #self.pos_animation.setDuration(200)
        #self.pos_animation.setStartValue(QPoint(1,0))
        #self.pos_animation.setEndValue(QPoint(1,-26))
        ##self.pos_animation.setEasingCurve()
        
    def onTogglePortCfgBar(self):
        #self.pos_animation.start()
        if self.frame_PortCfg.isVisible():
            self.setPortCfgBarVisible(False)
        else:
            self.setPortCfgBarVisible(True)

    def setPortCfgBarVisible(self, visible):
        if visible:
            self.frame_PortCfg.show()
            self.btnTogglePortCfgBar.setStyleSheet("QToolButton {image: url(:/up.png);}")
        else:
            self.frame_PortCfg.hide()
            self.btnTogglePortCfgBar.setStyleSheet("QToolButton {image: url(:/down.png);}")

    def onPortChanged(self, text):
        pos = text.find(' ')
        if 0 < pos:
            port_name = text[:pos]
            self.cmbPort.setCurrentText(port_name)

    def resizeEvent(self, event):
        if hasattr(self, '_maxBtn'):
            w = event.size().width()
            self._minBtn.move(w-112,0)
            self._maxBtn.move(w-81,0)
            self._closeBtn.move(w-50,0)

    def onMinimize(self):
        self.showMinimized()
    
    def isMaximized(self):
        return ((self.windowState() == Qt.WindowMaximized))
    
    def onMaximize(self):
        if self.isMaximized():
            self.showNormal()
            self.setMaximizeButton("maximize")
        else:
            self.showMaximized()
            self.setMaximizeButton("restore")
    
    def setMaximizeButton(self, style):
        if not hasattr(self, '_maxBtn'):
            return

        if "maximize" == style:
            self._maxBtn.setStyleSheet("""
                QPushButton {
                    background-color:transparent;
                    border:none;
                    outline: none;
                    image: url(:/maximize_inactive.png);
                }
                QPushButton:hover {
                    background-color:#227582;
                    image: url(:/maximize_active.png);
                }
                QPushButton:pressed {
                    background-color:#14464e;
                    image: url(:/maximize_active.png);
                }
            """)
        elif "restore" == style:
            self._maxBtn.setStyleSheet("""
                QPushButton {
                    background-color:transparent;
                    border:none;
                    outline: none;
                    image: url(:/restore_inactive.png);
                }
                QPushButton:hover {
                    background-color:#227582;
                    image: url(:/restore_active.png);
                }
                QPushButton:pressed {
                    background-color:#14464e;
                    image: url(:/restore_active.png);
                }
            """)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._isDragging = True
            self._dragPos = event.globalPos() - self.pos()
        event.accept()
        
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._isDragging and not self.isMaximized():
            self.move(event.globalPos() - self._dragPos)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._isDragging = False
        event.accept()

    def saveSettings(self):
        root = ET.Element(appInfo.title)
        GUISettings = ET.SubElement(root, "GUISettings")

        PortCfg = ET.SubElement(GUISettings, "PortConfig")
        ET.SubElement(PortCfg, "port").text = self.cmbPort.currentText()
        ET.SubElement(PortCfg, "baudrate").text = self.cmbBaudRate.currentText()
        ET.SubElement(PortCfg, "databits").text = self.cmbDataBits.currentText()
        ET.SubElement(PortCfg, "parity").text = self.cmbParity.currentText()
        ET.SubElement(PortCfg, "stopbits").text = self.cmbStopBits.currentText()
        ET.SubElement(PortCfg, "rtscts").text = self.chkRTSCTS.isChecked() and "on" or "off"
        ET.SubElement(PortCfg, "xonxoff").text = self.chkXonXoff.isChecked() and "on" or "off"

        View = ET.SubElement(GUISettings, "View")
        ET.SubElement(View, "LocalEcho").text = self.actionLocal_Echo.isChecked() and "on" or "off"
        ET.SubElement(View, "ReceiveView").text = self._viewGroup.checkedAction().text()

        with open(get_config_path(appInfo.title+'.xml'), 'w') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(ET.tostring(root, encoding='utf-8', pretty_print=True).decode("utf-8"))

    def loadSettings(self):
        if os.path.isfile(get_config_path(appInfo.title+".xml")):
            with open(get_config_path(appInfo.title+".xml"), 'r') as f:
                tree = safeET.parse(f)

            port = tree.findtext('GUISettings/PortConfig/port', default='')
            if port != '':
                self.cmbPort.setCurrentText(port)

            baudrate = tree.findtext('GUISettings/PortConfig/baudrate', default='38400')
            if baudrate != '':
                self.cmbBaudRate.setCurrentText(baudrate)

            databits = tree.findtext('GUISettings/PortConfig/databits', default='8')
            id = self.cmbDataBits.findText(databits)
            if id >= 0:
                self.cmbDataBits.setCurrentIndex(id)

            parity = tree.findtext('GUISettings/PortConfig/parity', default='None')
            id = self.cmbParity.findText(parity)
            if id >= 0:
                self.cmbParity.setCurrentIndex(id)

            stopbits = tree.findtext('GUISettings/PortConfig/stopbits', default='1')
            id = self.cmbStopBits.findText(stopbits)
            if id >= 0:
                self.cmbStopBits.setCurrentIndex(id)

            rtscts = tree.findtext('GUISettings/PortConfig/rtscts', default='off')
            if 'on' == rtscts:
                self.chkRTSCTS.setChecked(True)
            else:
                self.chkRTSCTS.setChecked(False)

            xonxoff = tree.findtext('GUISettings/PortConfig/xonxoff', default='off')
            if 'on' == xonxoff:
                self.chkXonXoff.setChecked(True)
            else:
                self.chkXonXoff.setChecked(False)

            LocalEcho = tree.findtext('GUISettings/View/LocalEcho', default='off')
            if 'on' == LocalEcho:
                self.actionLocal_Echo.setChecked(True)
                self._localEcho = True
            else:
                self.actionLocal_Echo.setChecked(False)
                self._localEcho = False

            ReceiveView = tree.findtext('GUISettings/View/ReceiveView', default='HEX(UPPERCASE)')
            if 'Ascii' in ReceiveView:
                self.actionAscii.setChecked(True)
                self._viewMode = VIEWMODE_ASCII
            elif 'lowercase' in ReceiveView:
                self.actionHex_lowercase.setChecked(True)
                self._viewMode = VIEWMODE_HEX_LOWERCASE
            elif 'UPPERCASE' in ReceiveView:
                self.actionHEX_UPPERCASE.setChecked(True)
                self._viewMode = VIEWMODE_HEX_UPPERCASE
            self.readerThread.setViewMode(self._viewMode)

    def closeEvent(self, event):
        if self.serialport.isOpen():
            self.closePort()
        self.saveLayout()
        self.saveQuickSend()
        self.saveSettings()
        event.accept()

    def initQuickSend(self):
        #self.quickSendTable.horizontalHeader().setDefaultSectionSize(40)
        #self.quickSendTable.horizontalHeader().setMinimumSectionSize(25)
        self.quickSendTable.setRowCount(50)
        self.quickSendTable.setColumnCount(3)
        self.quickSendTable.verticalHeader().setSectionsClickable(True)

        for row in range(50):
            self.initQuickSendButton(row, cmd = '%d' % (row+1))

        if os.path.isfile(get_config_path('QuickSend.csv')):
            self.loadQuickSend(get_config_path('QuickSend.csv'))

        self.quickSendTable.resizeColumnsToContents()

    def initQuickSendButton(self, row, cmd = 'cmd', opt = 'H', dat = ''):
        if self.quickSendTable.cellWidget(row, 0) is None:
            item = QToolButton(self)
            item.setText(cmd)
            item.clicked.connect(self._signalMapQuickSend.map)
            self._signalMapQuickSend.setMapping(item, row)
            self.quickSendTable.setCellWidget(row, 0, item)
        else:
            self.quickSendTable.cellWidget(row, 0).setText(cmd)

        if self.quickSendTable.cellWidget(row, 1) is None:
            item = QToolButton(self)
            item.setText(opt)
            #item.setMaximumSize(QtCore.QSize(16, 16))
            item.clicked.connect(self._signalMapQuickSendOpt.map)
            self._signalMapQuickSendOpt.setMapping(item, row)
            self.quickSendTable.setCellWidget(row, 1, item)
        else:
            self.quickSendTable.cellWidget(row, 1).setText(opt)

        if self.quickSendTable.item(row, 2) is None:
            self.quickSendTable.setItem(row, 2, QTableWidgetItem(dat))
        else:
            self.quickSendTable.item(row, 2).setText(dat)

        self.quickSendTable.setRowHeight(row, 20)

    def onSetSendHex(self):
        self.quickSendTable.cellWidget(self._quickSendOptRow, 1).setText('H')

    def onSetSendAsc(self):
        self.quickSendTable.cellWidget(self._quickSendOptRow, 1).setText('A')
        
    def onSetSendAscS(self):
        self.quickSendTable.cellWidget(self._quickSendOptRow, 1).setText('AS')

    def onSetSendHF(self):
        self.quickSendTable.cellWidget(self._quickSendOptRow, 1).setText('HF')

    def onSetSendAF(self):
        self.quickSendTable.cellWidget(self._quickSendOptRow, 1).setText('AF')

    def onSetSendBF(self):
        self.quickSendTable.cellWidget(self._quickSendOptRow, 1).setText('BF')

    def onQuickSendOptions(self, row):
        self._quickSendOptRow = row
        item = self.quickSendTable.cellWidget(row, 1)
        self.sendOptMenu.popup(item.mapToGlobal(QPoint(item.size().width(), item.size().height())))

    def openQuickSend(self):
        fileName = QFileDialog.getOpenFileName(self.defaultStyleWidget, "Select a file",
            os.getcwd(), "CSV Files (*.csv)")[0]
        if fileName:
            self.loadQuickSend(fileName, notifyExcept = True)

    def saveQuickSend(self):
        # scan table
        rows = self.quickSendTable.rowCount()

        save_data = [[self.quickSendTable.cellWidget(row, 0).text(),
                      self.quickSendTable.cellWidget(row, 1).text(),
                      self.quickSendTable.item(row, 2) is not None
                      and self.quickSendTable.item(row, 2).text() or ''] for row in range(rows)]

        #import pprint
        #pprint.pprint(save_data, width=120, compact=True)

        # write to file
        with open(get_config_path('QuickSend.csv'), 'w') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=',', lineterminator='\n')
            csvwriter.writerows(save_data)

    def loadQuickSend(self, path, notifyExcept = False):
        try:
            with open(path) as csvfile:
                csvData = csv.reader(csvfile)
                data = [row for row in csvData]
        except IOError as e:
            print("({})".format(e))
            if notifyExcept:
                QMessageBox.critical(self.defaultStyleWidget, "Open failed",
                    str(e), QMessageBox.Close)
        else:
            rows = self.quickSendTable.rowCount()

            if rows < len(data):
                rows = len(data) + 10
                self.quickSendTable.setRowCount(rows)

            for row, rowdat in enumerate(data):
                if len(rowdat) >= 3:
                    cmd, opt, dat = rowdat[0:3]
                    self.initQuickSendButton(row, cmd, opt, dat)

            self.quickSendTable.resizeColumnsToContents()
            #self.quickSendTable.resizeRowsToContents()

    def onQuickSend(self, row):
        if self.serialport.isOpen():
            if self.quickSendTable.item(row, 2) is not None:
                tablestring = self.quickSendTable.item(row, 2).text()
                form = self.quickSendTable.cellWidget(row, 1).text()
                if 'H' == form:
                    self.transmitHex(tablestring)
                elif 'A' == form:
                    self.transmitAsc(tablestring)
                elif 'AS' == form:
                    self.transmitAscS(tablestring)
                else:
                    self.transmitFile(tablestring, form)

    def transmitFile(self, filepath, form):
        try:
            with open(filepath, 'rb' if 'BF' == form else 'rt') as f:
                self.appendOutputText("\n%s sending %s [%s]" % (self.timestamp(), filepath, form), Qt.blue)
                self.repaint()
                
                content = f.read()
                sent_len = 0
                if 'HF' == form:
                    sent_len = self.transmitHex(content, echo = False)
                elif 'AF' == form:
                    sent_len = self.transmitAsc(content, echo = False)
                elif 'BF' == form:
                    sent_len = self.transmitBytearray(content)
                
                self.appendOutputText("\n%s %d bytes sent" % (self.timestamp(), sent_len), Qt.blue)
        except IOError as e:
            print("({})".format(e))
            QMessageBox.critical(self.defaultStyleWidget, "Open failed", str(e), QMessageBox.Close)

    def onPeriodicSend(self):
        if self._is_periodic_send:
            self.stopPeriodicSend()
        else:
            self.startPeriodicSend()

    def startPeriodicSend(self):
        period_spacing = int(self.spnPeriod.text()[:-2]) / 1000.0
        self.periodThread.start(period_spacing)
        self.btnPeriodicSend.setStyleSheet("QWidget {background-color:#b400c8}")
        self._is_periodic_send = True
            
    def stopPeriodicSend(self):
        self.periodThread.join()
        self.btnPeriodicSend.setStyleSheet("QWidget {}")
        self._is_periodic_send = False

    def onPeriodTrigger(self):
        self.onSend()
    
    def onSend(self):
        if self.serialport.isOpen():
            sendstring = self.txtEdtInput.toPlainText()
            self.transmitHex(sendstring)

    def transmitHex(self, hexstring, echo = True):
        if len(hexstring) > 0:
            hexarray = []
            _hexstring = hexstring.replace(' ', '')
            _hexstring = _hexstring.replace('\r', '')
            _hexstring = _hexstring.replace('\n', '')
            for i in range(0, len(_hexstring), 2):
                word = _hexstring[i:i+2]
                if is_hex(word):
                    hexarray.append(int(word, 16))
                else:
                    QMessageBox.critical(self.defaultStyleWidget, "Error",
                        "'%s' is not hexadecimal." % (word), QMessageBox.Close)
                    return 0
            if echo:
                text = ''.join('%02X ' % t for t in hexarray)
                self.appendOutputText("\n%s Tx:%s" % (self.timestamp(), text), Qt.blue)
            return self.transmitBytearray(bytearray(hexarray))

    def transmitAsc(self, text, echo = True):
        if len(text) > 0:
            byteArray = [ord(char) for char in text]
            if echo:
                self.appendOutputText("\n%s Tx:%s" % (self.timestamp(), text), Qt.blue)
            return self.transmitBytearray(bytearray(byteArray))

    def transmitAscS(self, text, echo = True):
        if len(text) > 0:
            t = text.replace(r'\r', '\r')
            t = t.replace(r'\n', '\n')
            t = t.replace(r'\t', '\t')
            t = t.replace(r'\'', "'")
            t = t.replace(r'\"', '"')
            t = t.replace(r'\\', '\\')
            self.transmitAsc(t, echo)

    def transmitBytearray(self, byteArray):
        if self.serialport.isOpen():
            try:
                self.serialport.write(byteArray)
            except Exception as e:
                QMessageBox.critical(self.defaultStyleWidget,
                    "Exception in transmit", str(e), QMessageBox.Close)
                print("Exception in transmitBytearray(%s)" % text)
                return 0
            else:
                return len(byteArray)

    def onReaderExcept(self, e):
        self.closePort()
        QMessageBox.critical(self.defaultStyleWidget, "Read failed", str(e), QMessageBox.Close)

    def timestamp(self):
        ts = datetime.datetime.now().time()
        if ts.microsecond:
            return ts.isoformat()[:-3]
        else:
            return ts.isoformat() + '.000'

    def onReceive(self, data):
        self.appendOutputText("\n%s R<-:%s" % (self.timestamp(), data))

    def appendOutputText(self, data, color=Qt.black):
        # the qEditText's "append" methon will add a unnecessary newline.
        # self.txtEdtOutput.append(data.decode('utf-8'))

        tc=self.txtEdtOutput.textColor()
        self.txtEdtOutput.moveCursor(QtGui.QTextCursor.End)
        self.txtEdtOutput.setTextColor(QtGui.QColor(color))
        self.txtEdtOutput.insertPlainText(data)
        self.txtEdtOutput.moveCursor(QtGui.QTextCursor.End)
        self.txtEdtOutput.setTextColor(tc)

    def getPort(self):
        return self.cmbPort.currentText()

    def getDataBits(self):
        return {'5':serial.FIVEBITS,
                '6':serial.SIXBITS,
                '7':serial.SEVENBITS, 
                '8':serial.EIGHTBITS}[self.cmbDataBits.currentText()]

    def getParity(self):
        return {'None' :serial.PARITY_NONE,
                'Even' :serial.PARITY_EVEN,
                'Odd'  :serial.PARITY_ODD,
                'Mark' :serial.PARITY_MARK,
                'Space':serial.PARITY_SPACE}[self.cmbParity.currentText()]

    def getStopBits(self):
        return {'1'  :serial.STOPBITS_ONE,
                '1.5':serial.STOPBITS_ONE_POINT_FIVE,
                '2'  :serial.STOPBITS_TWO}[self.cmbStopBits.currentText()]

    def openPort(self):
        if self.serialport.isOpen():
            return

        _port = self.getPort()
        if '' == _port:
            QMessageBox.information(self.defaultStyleWidget, "Invalid parameters", "Port is empty.")
            return

        _baudrate = self.cmbBaudRate.currentText()
        if '' == _baudrate:
            QMessageBox.information(self.defaultStyleWidget, "Invalid parameters", "Baudrate is empty.")
            return

        self.serialport.port     = _port
        self.serialport.baudrate = _baudrate
        self.serialport.bytesize = self.getDataBits()
        self.serialport.stopbits = self.getStopBits()
        self.serialport.parity   = self.getParity()
        self.serialport.rtscts   = self.chkRTSCTS.isChecked()
        self.serialport.xonxoff  = self.chkXonXoff.isChecked()
        self.serialport.timeout  = 0.5
        # self.serialport.writeTimeout = 1.0
        try:
            self.serialport.open()
        except Exception as e:
            QMessageBox.critical(self.defaultStyleWidget, 
                "Could not open serial port", str(e), QMessageBox.Close)
        else:
            self.readerThread.start()
            self.setWindowTitle("%s on %s [%s, %s%s%s%s%s]" % (
                appInfo.title,
                self.serialport.portstr,
                self.serialport.baudrate,
                self.serialport.bytesize,
                self.serialport.parity,
                self.serialport.stopbits,
                self.serialport.rtscts and ' RTS/CTS' or '',
                self.serialport.xonxoff and ' Xon/Xoff' or '',
                )
            )
            self.cmbPort.setEnabled(False)
            self.cmbPort.setStyleSheet('QComboBox:editable {background: yellow;}')
            self.btnOpen.setText('Close')
            self.btnOpen.update()

    def closePort(self):
        if self.serialport.isOpen():
            self.stopPeriodicSend()
            self.readerThread.join()
            self.portMonitorThread.join()
            self.serialport.close()
            self.setWindowTitle(appInfo.title)
            self.cmbPort.setEnabled(True)
            self.cmbPort.setStyleSheet('QComboBox:editable {background: white;}')
            self.btnOpen.setText('Open')
            self.btnOpen.update()

    #def onTogglePrtCfgPnl(self):
        #if self.actionPort_Config_Panel.isChecked():
            #self.dockWidget_PortConfig.show()
        #else:
            #self.dockWidget_PortConfig.hide()

    def onToggleQckSndPnl(self):
        if self.actionQuick_Send_Panel.isChecked():
            self.dockWidget_QuickSend.show()
        else:
            self.dockWidget_QuickSend.hide()

    def onToggleHexPnl(self):
        if self.actionSend_Hex_Panel.isChecked():
            self.dockWidget_SendHex.show()
        else:
            self.dockWidget_SendHex.hide()

    def onVisiblePrtCfgPnl(self, visible):
        self.actionPort_Config_Panel.setChecked(visible)

    def onVisibleQckSndPnl(self, visible):
        self.actionQuick_Send_Panel.setChecked(visible)

    def onVisibleHexPnl(self, visible):
        self.actionSend_Hex_Panel.setChecked(visible)

    def onLocalEcho(self):
        self._localEcho = self.actionLocal_Echo.isChecked()

    def onAlwaysOnTop(self):
        if self.actionAlways_On_Top.isChecked():
            style = self.windowFlags()
            self.setWindowFlags(style|Qt.WindowStaysOnTopHint)
            self.show()
        else:
            style = self.windowFlags()
            self.setWindowFlags(style & ~Qt.WindowStaysOnTopHint)
            self.show()

    def onOpen(self):
        if self.serialport.isOpen():
            self.closePort()
        else:
            self.openPort()

    def onClear(self):
        self.txtEdtOutput.clear()

    def onSaveLog(self):
        fileName = QFileDialog.getSaveFileName(self.defaultStyleWidget, "Save as", os.getcwd(),
            "Log files (*.log);;Text files (*.txt);;All files (*.*)")[0]
        if fileName:
            import codecs
            with codecs.open(fileName, 'w', 'utf-8') as f:
                f.write(self.txtEdtOutput.toPlainText())

    def moveScreenCenter(self):
        w = self.frameGeometry().width()
        h = self.frameGeometry().height()
        desktop = QDesktopWidget()
        screenW = desktop.screen().width()
        screenH = desktop.screen().height()
        self.setGeometry((screenW-w)/2, (screenH-h)/2, w, h)

        w = self.defaultStyleWidget.frameGeometry().width()
        h = self.defaultStyleWidget.frameGeometry().height()
        self.defaultStyleWidget.setGeometry((screenW-w)/2, (screenH-h)/2, w, h)

    def onEnumPorts(self):
        sel = self.cmbPort.currentText()
        self.cmbPort.clear()
        fm = QFontMetrics(self.cmbPort.fontMetrics())
        maxlen = 0
        for port, desc, hwid in sorted(comports()):
            text = port + '  ' + desc
            self.cmbPort.addItem(text)
            if hasattr(fm, 'horizontalAdvance'):
                l = fm.horizontalAdvance(text)
            else:
                l = fm.width(text)
            if maxlen < l:
                maxlen = l
        self.cmbPort.view().setFixedWidth(maxlen+40)
        
        idx = self.cmbPort.findText(sel)
        if idx != -1:
            self.cmbPort.setCurrentIndex(idx)

    def onAbout(self):
        QMessageBox.about(self.defaultStyleWidget, "About MyTerm", appInfo.aboutme)

    def onAboutQt(self):
        QMessageBox.aboutQt(self.defaultStyleWidget)

    def onExit(self):
        if self.serialport.isOpen():
            self.closePort()
        self.close()

    def restoreLayout(self):
        if os.path.isfile(get_config_path("UILayout.dat")):
            try:
                f=open(get_config_path("UILayout.dat"), 'rb')
                geometry, state=pickle.load(f)
                self.restoreGeometry(geometry)
                self.restoreState(state)
            except Exception as e:
                print("Exception on restoreLayout, {}".format(e))
        else:
            try:
                f=QFile(':/default_layout.dat')
                f.open(QIODevice.ReadOnly)
                geometry, state=pickle.loads(f.readAll())
                self.restoreGeometry(geometry)
                self.restoreState(state)
            except Exception as e:
                print("Exception on restoreLayout, {}".format(e))

    def saveLayout(self):
        with open(get_config_path("UILayout.dat"), 'wb') as f:
            pickle.dump((self.saveGeometry(), self.saveState()), f)

    def syncMenu(self):
        #self.actionPort_Config_Panel.setChecked(not self.dockWidget_PortConfig.isHidden())
        self.actionQuick_Send_Panel.setChecked(not self.dockWidget_QuickSend.isHidden())
        self.actionSend_Hex_Panel.setChecked(not self.dockWidget_SendHex.isHidden())

    def onViewChanged(self):
        checked = self._viewGroup.checkedAction()
        if checked is None:
            self._viewMode = VIEWMODE_HEX_UPPERCASE
            self.actionHEX_UPPERCASE.setChecked(True)
        else:
            if 'Ascii' in checked.text():
                self._viewMode = VIEWMODE_ASCII
            elif 'lowercase' in checked.text():
                self._viewMode = VIEWMODE_HEX_LOWERCASE
            elif 'UPPERCASE' in checked.text():
                self._viewMode = VIEWMODE_HEX_UPPERCASE

        self.readerThread.setViewMode(self._viewMode)

def is_hex(s):
    try:
        int(s, 16)
        return True
    except ValueError:
        return False



class ReaderThread(QThread):
    """loop and copy serial->GUI"""
    read = pyqtSignal(str)
    exception = pyqtSignal(str)

    def __init__(self, parent=None):
        super(ReaderThread, self).__init__(parent)
        self._alive = False
        self._stopped = True
        self._serialport = None
        self._viewMode = None

    def setPort(self, port):
        self._serialport = port

    def setViewMode(self, mode):
        self._viewMode = mode

    def start(self, priority = QThread.InheritPriority):
        if not self._alive:
            self._alive = True
            super(ReaderThread, self).start(priority)

    def __del__(self):
        if self._alive:
            self._alive = False
            if hasattr(self._serialport, 'cancel_read'):
                self._serialport.cancel_read()
            else:
                self._serialport.close()
        if not self._stopped:
            self.wait()

    def join(self):
        self.__del__()

    def run(self):
        self._stopped = False
        text = str()
        try:
            while self._alive:
                # read all that is there or wait for one byte
                data = self._serialport.read(self._serialport.inWaiting() or 1)
                if not self._alive:
                    return
                else:
                    sleep(0.05)
                if self._serialport.inWaiting():
                    data = data + self._serialport.read(self._serialport.inWaiting())
                if data:
                    try:
                        if self._viewMode == VIEWMODE_ASCII:
                            text = data.decode('unicode_escape')
                        elif self._viewMode == VIEWMODE_HEX_LOWERCASE:
                            text = ''.join('%02x ' % t for t in data)
                        elif self._viewMode == VIEWMODE_HEX_UPPERCASE:
                            text = ''.join('%02X ' % t for t in data)
                    except UnicodeDecodeError:
                        pass
                    else:
                        self.read.emit(text)
        except Exception as e:
            self.exception.emit('{}'.format(e))
        self._stopped = True

class PortMonitorThread(QThread):
    portPlugOut = pyqtSignal()
    exception = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super(PortMonitorThread, self).__init__(parent)
        self._alive = False
        self._stopped = True
        self._serialport = None

    def setPort(self, port):
        self._serialport = port

    def start(self, priority = QThread.InheritPriority):
        if not self._alive:
            self._alive = True
            super(PortMonitorThread, self).start(priority)

    def __del__(self):
        self._alive = False
        if not self._stopped:
            self.wait()

    def join(self):
        self.__del__()

    def run(self):
        self._stopped = False
        while self._alive:
            try:
                port_lst = [port for port, desc, hwid in sorted(comports())]
                if self._serialport.portstr not in port_lst:
                    self.portPlugOut.emit()
                sleep(0.5)
            except Exception as e:
                self.exception.emit('{}'.format(e))
        self._stopped = True

class PeriodThread(QThread):
    trigger = pyqtSignal()
    exception = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super(PeriodThread, self).__init__(parent)
        self._alive = False
        self._stopped = True
        self._spacing = 1.0

    def start(self, period_spacing, priority = QThread.InheritPriority):
        if not self._alive:
            self._alive = True
            self._spacing = period_spacing
            super(PeriodThread, self).start(priority)

    def __del__(self):
        self._alive = False
        if not self._stopped:
            self.wait()

    def join(self):
        self.__del__()

    def run(self):
        self._stopped = False
        while self._alive:
            try:
                self.trigger.emit()
                sleep(self._spacing)
            except Exception as e:
                self.exception.emit('{}'.format(e))
        self._stopped = True

if __name__ == '__main__':
    app = QApplication(sys.argv)
    frame = MainWindow()
    frame.show()
    app.exec_()
