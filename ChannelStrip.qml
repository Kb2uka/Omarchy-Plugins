import QtQuick
import QtQuick.Controls
import "Palette.js" as P

Rectangle {
  id: root
  required property var channel
  property bool available: true
  property bool prominent: false
  readonly property bool adjustable: channel.adjustable !== false
  readonly property bool known: channel.db !== null && channel.db !== undefined && isFinite(Number(channel.db))
  readonly property bool restorable: channel.restore_db !== null && channel.restore_db !== undefined && isFinite(Number(channel.restore_db))
  readonly property bool measured: channel.peak !== null && channel.peak !== undefined && isFinite(Number(channel.peak))
  readonly property real meterRatio: available && measured ? Math.max(0, Math.min(1, (Number(channel.peak) + 60) / 60)) : 0
  readonly property real stepDb: Number(channel.step) || 1
  readonly property real gainMin: Number(channel.min) || 0
  readonly property real gainMax: Number(channel.max) || 0
  readonly property string label: channel.id === "out1" ? "Monitor L" : channel.id === "out2" ? "Monitor R" : channel.id === "out3" ? "Phones L" : channel.id === "out4" ? "Phones R" : channel.id === "mic1" ? "Mic 1" : channel.id === "mic2" ? "Mic 2" : channel.id === "line3" ? "Line 3" : channel.id === "line4" ? "Line 4" : channel.label
  property bool gestureDirty: false
  property var activeControl: null
  signal gainRequested(string channelId, var db)
  objectName: "channel-" + channel.id
  implicitHeight: P.channelHeight
  radius: P.radius.panel
  border.width: 1
  border.color: P.border
  gradient: Gradient {
    GradientStop { position: 0; color: P.elevated }
    GradientStop { position: 0.18; color: P.surface }
    GradientStop { position: 1; color: P.background }
  }
  Rectangle { anchors.fill: parent; anchors.margins: 2; radius: parent.radius - 1; color: "transparent"; border.color: P.highlight; border.width: 1; opacity: 0.62 }

  function setGain(value) {
    if (!available || !adjustable || !isFinite(value)) return
    var quantized = Math.round((value - gainMin) / stepDb) * stepDb + gainMin
    gainRequested(String(channel.id), Math.max(gainMin, Math.min(gainMax, quantized)))
  }
  function moved(control) {
    if (control.pressed) {
      activeControl = control
      gestureDirty = true
      if (!dragCommit.running) dragCommit.start()
    } else setGain(control.value)
  }
  function released(control) {
    if (activeControl !== control) return
    dragCommit.stop()
    setGain(control.value)
    gestureDirty = false
    activeControl = null
  }
  function syncControls() {
    if (!channel.pending) {
      var value = known ? Number(channel.db) : channel.muted && restorable ? Number(channel.restore_db) : gainMin
      if (!slider.pressed) slider.value = value
      if (!knob.pressed) knob.value = value
    }
  }
  onChannelChanged: Qt.callLater(root.syncControls)
  Component.onCompleted: syncControls()
  onAvailableChanged: if (!available) { dragCommit.stop(); gestureDirty = false; activeControl = null }
  Timer {
    id: dragCommit
    interval: 80
    onTriggered: if (root.activeControl && root.activeControl.pressed && root.gestureDirty) {
      root.setGain(root.activeControl.value)
      root.gestureDirty = false
    }
  }

  Column {
    objectName: "channel-content"
    anchors.fill: parent
    anchors.margins: P.spacing.section
    spacing: P.spacing.small
    Row {
      width: parent.width; height: 22
      Text { width: parent.width - port.width; text: root.label; color: P.text; font.family: P.font; font.pixelSize: 18; font.weight: Font.DemiBold; elide: Text.ElideRight }
      Text { id: port; text: root.channel.port; color: P.secondary; font.family: P.font; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter; font.letterSpacing: 0.5 }
    }
    Rectangle {
      width: parent.width; height: root.prominent ? 168 : 154
      color: P.control; radius: 2
      border.color: P.edge; border.width: 1
      gradient: Gradient { GradientStop { position: 0; color: P.control } GradientStop { position: 1; color: P.surface } }
      LevelMeter { x: 4; y: 10; height: parent.height - 16; peak: root.channel.peak; available: root.available }
      Item {
        x: 62; y: root.prominent ? 12 : 6
        width: Math.max(90, parent.width - 106); height: parent.height - 8
        RotaryKnob {
          id: knob
          objectName: "gain-knob"
          anchors.horizontalCenter: parent.horizontalCenter
          width: Math.min(118, parent.width); height: width
          sweepAngle: root.channel.group === "output" ? 180 : 270
          from: root.gainMin; to: Math.max(root.gainMin + root.stepDb, root.gainMax); stepSize: root.stepDb
          enabled: root.available && root.adjustable
          Accessible.name: root.label + " rotary gain in decibels"
          onMoved: root.moved(knob)
          onPressedChanged: if (!pressed) root.released(knob)
        }
        Text {
          objectName: "gain-value"
          anchors.horizontalCenter: parent.horizontalCenter
          y: knob.height + 2
          text: (root.channel.muted ? "−∞" : !root.known ? "—" : (Number(root.channel.db) > 0 ? "+" : "") + Number(root.channel.db).toFixed(1)) + " dB"
          color: root.available ? P.text : P.muted
          font.family: P.font; font.pixelSize: 20
        }
      }
      Column {
        anchors.right: parent.right; anchors.rightMargin: 3
        anchors.verticalCenter: parent.verticalCenter
        spacing: P.spacing.medium
        StudioButton {
          objectName: "decrease"; text: "−"; implicitWidth: 40; implicitHeight: 40
          enabled: root.available && root.adjustable && root.known && !root.channel.muted && Number(root.channel.db) > root.gainMin
          Accessible.name: "Decrease " + root.channel.label + " gain"
          onClicked: root.setGain(Number(root.channel.db) - root.stepDb)
        }
        StudioButton {
          objectName: "increase"; text: "+"; implicitWidth: 40; implicitHeight: 40
          enabled: root.available && root.adjustable && root.known && Number(root.channel.db) < root.gainMax
          Accessible.name: "Increase " + root.channel.label + " gain"
          onClicked: root.setGain(Number(root.channel.db) + root.stepDb)
        }
      }
    }
    AudioFader {
      id: slider
      objectName: "gain-slider"
      width: parent.width
      from: root.gainMin; to: Math.max(root.gainMin + root.stepDb, root.gainMax); stepSize: root.stepDb
      enabled: root.available && root.adjustable
      Accessible.name: root.channel.label + " gain in decibels"
      onMoved: root.moved(slider)
      onPressedChanged: if (!pressed) root.released(slider)
    }
    Rectangle {
      width: parent.width; height: 7; color: P.control
      border.color: P.edge; border.width: 1; radius: 2
      Rectangle {
        x: 1; y: 2; width: parent.width - 2; height: 3
        color: root.measured && Number(root.channel.peak) >= 0 ? P.danger : P.accent
        transform: Scale { origin.x: 0; xScale: root.meterRatio; Behavior on xScale { NumberAnimation { duration: 80 } } }
        opacity: 0.5
      }
    }
    Row {
      width: parent.width; height: 18
      Text {
        width: parent.width - peakText.width
        text: root.channel.pending ? "APPLYING…" : !root.adjustable ? "DIGITAL · UNITY" : root.channel.readback === false ? "LAST SOFTWARE SETTING" : "HARDWARE GAIN"
        color: P.secondary; font.family: P.font; font.pixelSize: 10; elide: Text.ElideRight
      }
      Text { id: peakText; text: root.measured && root.available ? Number(root.channel.peak).toFixed(1) + " dBFS" : "— dBFS"; color: P.secondary; font.family: P.mono; font.pixelSize: 10 }
    }
    StudioButton {
      objectName: "mute-output"
      visible: root.channel.group === "output"
      text: root.channel.muted ? (root.restorable ? "UNMUTE OUTPUT" : "SET GAIN TO UNMUTE") : "MUTE OUTPUT"
      primary: root.channel.muted === true
      implicitHeight: 40; width: parent.width
      enabled: root.available && !root.channel.pending && (!root.channel.muted || root.restorable)
      Accessible.name: (root.channel.muted ? "Unmute " : "Mute ") + root.channel.label
      onClicked: {
        if (!enabled) return
        root.gainRequested(String(root.channel.id), root.channel.muted ? Number(root.channel.restore_db) : null)
      }
    }
    Rectangle {
      visible: root.channel.group === "input"
      width: parent.width; height: 40; radius: P.radius.control
      color: P.control; border.color: P.edge; border.width: 1
      Text {
        anchors.centerIn: parent
        text: root.adjustable ? (root.channel.id.indexOf("mic") === 0 ? "PREAMP" : "LINE / INSTRUMENT") + "    " + root.gainMin + " – " + root.gainMax + " dB" : "DIGITAL INPUT · FIXED UNITY"
        color: P.secondary; font.family: P.font; font.pixelSize: 10; font.letterSpacing: 0.4
      }
    }
  }
}
