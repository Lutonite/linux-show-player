# This file is part of Linux Show Player
#
# Copyright 2016 Francesco Ceruti <ceppofrancy@gmail.com>
#
# Linux Show Player is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Linux Show Player is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Linux Show Player.  If not, see <http://www.gnu.org/licenses/>.
import logging

from PyQt5.QtCore import Qt, QT_TRANSLATE_NOOP
from PyQt5.QtWidgets import (
    QGroupBox,
    QPushButton,
    QComboBox,
    QVBoxLayout,
    QMessageBox,
    QTableView,
    QTableWidget,
    QHeaderView,
    QGridLayout,
    QLabel,
    QHBoxLayout,
)
from mido.messages import Message

from lisp.application import Application
from lisp.backend.audio_utils import slider_to_fader
from lisp.core.plugin import PluginNotLoadedError
from lisp.cues.cue import Cue, CueState
from lisp.cues.media_cue import MediaCue
from lisp.plugins import get_plugin
from lisp.plugins.cart_layout.layout import CartLayout
from lisp.plugins.controller.common import LayoutAction, tr_layout_action
from lisp.plugins.controller.devices.apc_midi_mk1 import ApcButtonRange, ApcPushButtonColor, note_in_range, \
    ApcSideButtonColor
from lisp.plugins.controller.protocol import Protocol
from lisp.plugins.midi.midi_utils import (
    MIDI_MSGS_NAME,
    midi_data_from_msg,
    midi_msg_from_data,
    midi_from_dict,
    midi_from_str,
    MIDI_MSGS_SPEC,
    MIDI_ATTRS_SPEC,
)
from lisp.plugins.midi.widgets import MIDIMessageEditDialog
from lisp.ui.qdelegates import (
    CueActionDelegate,
    EnumComboBoxDelegate,
    LabelDelegate,
)
from lisp.ui.qmodels import SimpleTableModel
from lisp.ui.settings.pages import CuePageMixin, SettingsPage
from lisp.ui.ui_utils import translate

logger = logging.getLogger(__name__)


class MidiSettings(SettingsPage):
    FILTER_ALL = "__all__"

    Name = QT_TRANSLATE_NOOP("SettingsPageName", "MIDI Controls")

    def __init__(self, actionDelegate, **kwargs):
        super().__init__(**kwargs)
        self.setLayout(QVBoxLayout())
        self.layout().setAlignment(Qt.AlignTop)

        self.midiGroup = QGroupBox(self)
        self.midiGroup.setTitle(translate("ControllerMidiSettings", "MIDI"))
        self.midiGroup.setLayout(QGridLayout())
        self.layout().addWidget(self.midiGroup)

        self.midiModel = MidiModel()

        self.midiView = MidiView(actionDelegate, parent=self.midiGroup)
        self.midiView.setModel(self.midiModel)
        self.midiGroup.layout().addWidget(self.midiView, 0, 0, 1, 2)

        self.addButton = QPushButton(self.midiGroup)
        self.addButton.clicked.connect(self.__new_message)
        self.midiGroup.layout().addWidget(self.addButton, 1, 0)

        self.removeButton = QPushButton(self.midiGroup)
        self.removeButton.clicked.connect(self.__remove_message)
        self.midiGroup.layout().addWidget(self.removeButton, 1, 1)

        self.midiCapture = QPushButton(self.midiGroup)
        self.midiCapture.clicked.connect(self.capture_message)
        self.midiGroup.layout().addWidget(self.midiCapture, 2, 0)

        self.filterLayout = QHBoxLayout()
        self.midiGroup.layout().addLayout(self.filterLayout, 2, 1)

        self.filterLabel = QLabel(self.midiGroup)
        self.filterLabel.setAlignment(Qt.AlignCenter)
        self.filterLayout.addWidget(self.filterLabel)

        self.filterTypeCombo = QComboBox(self.midiGroup)
        self.filterLayout.addWidget(self.filterTypeCombo)

        self.filterTypeCombo.addItem(
            translate("ControllerMidiSettings", "-- All Messages --"),
            self.FILTER_ALL,
        )
        for msg_type, msg_name in MIDI_MSGS_NAME.items():
            self.filterTypeCombo.addItem(
                translate("MIDIMessageType", msg_name), msg_type
            )

        self.retranslateUi()

        self._defaultAction = None
        try:
            self.__midi = get_plugin("Midi")
        except PluginNotLoadedError:
            self.setEnabled(False)

    def retranslateUi(self):
        self.addButton.setText(translate("ControllerSettings", "Add"))
        self.removeButton.setText(translate("ControllerSettings", "Remove"))

        self.midiCapture.setText(translate("ControllerMidiSettings", "Capture"))
        self.filterLabel.setText(
            translate("ControllerMidiSettings", "Capture filter")
        )

    def enableCheck(self, enabled):
        self.setGroupEnabled(self.midiGroup, enabled)

    def getSettings(self):
        entries = []
        for row in range(self.midiModel.rowCount()):
            message, action = self.midiModel.getMessage(row)
            entries.append((str(message), action))

        return {"midi": entries}

    def loadSettings(self, settings):
        for entry in settings.get("midi", ()):
            try:
                self.midiModel.appendMessage(midi_from_str(entry[0]), entry[1])
            except Exception:
                logger.warning(
                    translate(
                        "ControllerMidiSettingsWarning",
                        "Error while importing configuration entry, skipped.",
                    ),
                    exc_info=True,
                )

    def capture_message(self):
        handler = self.__midi.input
        handler.alternate_mode = True
        handler.new_message_alt.connect(self.__add_message)

        QMessageBox.information(
            self,
            "",
            translate("ControllerMidiSettings", "Listening MIDI messages ..."),
        )

        handler.new_message_alt.disconnect(self.__add_message)
        handler.alternate_mode = False

    def __add_message(self, message):
        mgs_filter = self.filterTypeCombo.currentData(Qt.UserRole)
        if mgs_filter == self.FILTER_ALL or message.type == mgs_filter:
            if hasattr(message, "velocity"):
                message = message.copy(velocity=0)

            self.midiModel.appendMessage(message, self._defaultAction)

    def __new_message(self):
        dialog = MIDIMessageEditDialog()
        if dialog.exec() == MIDIMessageEditDialog.Accepted:
            message = midi_from_dict(dialog.getMessageDict())
            if hasattr(message, "velocity"):
                message.velocity = 0

            self.midiModel.appendMessage(message, self._defaultAction)

    def __remove_message(self):
        self.midiModel.removeRow(self.midiView.currentIndex().row())


class MidiCueSettings(MidiSettings, CuePageMixin):
    def __init__(self, cueType, **kwargs):
        super().__init__(
            actionDelegate=CueActionDelegate(
                cue_class=cueType, mode=CueActionDelegate.Mode.Name
            ),
            cueType=cueType,
            **kwargs,
        )
        self._defaultAction = self.cueType.CueActions[0].name


class MidiLayoutSettings(MidiSettings):
    def __init__(self, **kwargs):
        super().__init__(
            actionDelegate=EnumComboBoxDelegate(
                LayoutAction,
                mode=EnumComboBoxDelegate.Mode.Name,
                trItem=tr_layout_action,
            ),
            **kwargs,
        )
        self._defaultAction = LayoutAction.Go.name


class MidiMessageTypeDelegate(LabelDelegate):
    def _text(self, option, index):
        message_type = index.data()
        return translate(
            "MIDIMessageType", MIDI_MSGS_NAME.get(message_type, "undefined")
        )


class MidiValueDelegate(LabelDelegate):
    def _text(self, option, index):
        option.displayAlignment = Qt.AlignCenter

        value = index.data()
        if value is not None:
            model = index.model()
            message_type = model.data(model.index(index.row(), 0))
            message_spec = MIDI_MSGS_SPEC.get(message_type, ())

            if len(message_spec) >= index.column():
                attr = message_spec[index.column() - 1]
                attr_spec = MIDI_ATTRS_SPEC.get(attr)

                if attr_spec is not None:
                    return str(value - attr_spec[-1])

        return ""


class MidiModel(SimpleTableModel):
    def __init__(self):
        super().__init__(
            [
                translate("ControllerMidiSettings", "Type"),
                translate("ControllerMidiSettings", "Data 1"),
                translate("ControllerMidiSettings", "Data 2"),
                translate("ControllerMidiSettings", "Data 3"),
                translate("ControllerMidiSettings", "Action"),
            ]
        )

    def appendMessage(self, message, action):
        data = midi_data_from_msg(message)
        data.extend((None,) * (3 - len(data)))
        self.appendRow(message.type, *data, action)

    def updateMessage(self, row, message, action):
        data = midi_data_from_msg(message)
        data.extend((None,) * (3 - len(data)))
        self.updateRow(row, message.type, *data, action)

    def getMessage(self, row):
        if row < len(self.rows):
            return (
                midi_msg_from_data(self.rows[row][0], self.rows[row][1:4]),
                self.rows[row][4],
            )

    def flags(self, index):
        if index.column() <= 3:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        else:
            return super().flags(index)


class MidiView(QTableView):
    def __init__(self, actionDelegate, **kwargs):
        super().__init__(**kwargs)

        self.delegates = [
            MidiMessageTypeDelegate(),
            MidiValueDelegate(),
            MidiValueDelegate(),
            MidiValueDelegate(),
            actionDelegate,
        ]

        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableView.SingleSelection)

        self.setShowGrid(False)
        self.setAlternatingRowColors(True)

        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.horizontalHeader().setMinimumSectionSize(80)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setHighlightSections(False)

        self.verticalHeader().sectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setDefaultSectionSize(24)
        self.verticalHeader().setHighlightSections(False)

        for column, delegate in enumerate(self.delegates):
            self.setItemDelegateForColumn(column, delegate)

        self.doubleClicked.connect(self.__doubleClicked)

    def __doubleClicked(self, index):
        if index.column() <= 3:
            message, action = self.model().getMessage(index.row())

            dialog = MIDIMessageEditDialog()
            dialog.setMessageDict(message.dict())

            if dialog.exec() == MIDIMessageEditDialog.Accepted:
                self.model().updateMessage(
                    index.row(), midi_from_dict(dialog.getMessageDict()), action
                )


previous_page_button = ApcButtonRange.BottomSide[0] + 2
next_page_button = ApcButtonRange.BottomSide[0] + 3
stop_all_button = ApcButtonRange.RightSide[1]
shift_button = ApcButtonRange.Shift[0]


class Midi(Protocol):
    CueSettings = MidiCueSettings
    LayoutSettings = MidiLayoutSettings

    def __init__(self):
        super().__init__()
        # Install callback for new MIDI messages
        get_plugin("Midi").input.new_message.connect(self.__new_message)
        self._midi_output = get_plugin("Midi").output
        self._shift = False

    def init(self):
        Application().cue_model.status_changed.connect(self.__cue_status_changed)

    def reset(self):
        Application().cue_model.status_changed.disconnect(self.__cue_status_changed)

    def __new_message(self, message: Message):
        # TODO: hack to support shift key on APC mini, I'd like to support this cleanly through device bindings
        if not self._shift and getattr(message, "type") == "note_on" and getattr(message, "note") == shift_button:
            self._enable_shift_mode()
            return

        if self._shift and getattr(message, "type") == "note_off" and getattr(message, "note") == shift_button:
            self._disable_shift_mode()
            return

        if self._shift and getattr(message, "type") == "note_on":
            note = getattr(message, "note")
            if note == stop_all_button:
                Application().layout.stop_all()
                self._send_feedback(stop_all_button, ApcSideButtonColor.Blink)
                return
            elif note == previous_page_button:
                if isinstance(Application().layout, CartLayout):
                    Application().layout.select_previous_page()
                return
            elif note == next_page_button:
                if isinstance(Application().layout, CartLayout):
                    Application().layout.select_next_page()
                return

        if getattr(message, "type") == "control_change":
            if getattr(message, "control") == ApcButtonRange.Faders[1]:
                # TODO: master gain?
                return

            if isinstance(Application().layout, CartLayout):
                column = getattr(message, "control") - ApcButtonRange.Faders[0]
                for cue in Application().layout.cues_at_column(column, MediaCue):
                    volume = cue.media.element("Volume")
                    if volume is not None:
                        volume.live_volume = getattr(message, "value") / 127

        if hasattr(message, "velocity"):
            message = message.copy(velocity=0)

        self.protocol_event.emit(str(message))

    def __cue_status_changed(self, cue: Cue):
        for key, _ in cue.controller.get('midi', []):
            note = midi_from_str(key).note
            if not note_in_range(note, ApcButtonRange.PushButton):
                continue

            if cue.state & CueState.IsRunning:
                self._send_feedback(note, ApcPushButtonColor.Green)
            elif cue.state & CueState.IsPaused:
                self._send_feedback(note, ApcPushButtonColor.GreenBlink)
            elif cue.state & CueState.IsStopped:
                self._send_feedback(note, ApcPushButtonColor.Yellow)

    def _send_feedback(self, key, color):
        message = Message("note_on", channel=0, note=key, velocity=color)
        if self._midi_output.is_open():
            self._midi_output.send(message)

    def _enable_shift_mode(self):
        if self._shift:
            return

        self._shift = True
        self._send_feedback(ApcButtonRange.RightSide[1], ApcSideButtonColor.On)
        self._send_feedback(previous_page_button, ApcSideButtonColor.On)
        self._send_feedback(next_page_button, ApcSideButtonColor.On)

    def _disable_shift_mode(self):
        if not self._shift:
            return

        self._shift = False
        self._send_feedback(ApcButtonRange.RightSide[1], ApcSideButtonColor.Off)
        self._send_feedback(previous_page_button, ApcSideButtonColor.Off)
        self._send_feedback(next_page_button, ApcSideButtonColor.Off)
