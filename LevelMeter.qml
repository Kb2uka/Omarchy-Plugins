import QtQuick
import "Palette.js" as P

Item {
  id: root
  property var peak: null
  property bool available: true
  readonly property bool measured: available && peak !== null && peak !== undefined && isFinite(Number(peak))
  readonly property real ratio: measured ? Math.max(0, Math.min(1, (Number(peak) + 60) / 60)) : 0
  property real heldPeak: -100
  readonly property bool clipping: measured && heldPeak >= 0
  implicitWidth: 52
  implicitHeight: 142
  onPeakChanged: {
    if (measured && Number(peak) >= heldPeak) {
      heldPeak = Number(peak)
      release.restart()
    }
  }
  onAvailableChanged: if (!available) heldPeak = -100
  Timer { id: release; interval: 1100; onTriggered: root.heldPeak = root.measured ? Number(root.peak) : -100 }
  Rectangle {
    id: well
    width: 18; height: parent.height
    color: P.control
    border.color: P.edge
    border.width: 1
    Item {
      id: lamps
      x: 4; y: 5; width: 10; height: parent.height - 10
      Repeater {
        model: 28
        Rectangle {
          required property int index
          x: 0; y: index * (lamps.height / 28)
          width: lamps.width; height: Math.max(2, lamps.height / 28 - 2)
          color: index === 0 ? P.danger : index < 7 ? P.amber : P.safe
          opacity: 0.1
        }
      }
      Item {
        anchors.fill: parent
        clip: true
        Rectangle {
          id: lit
          anchors.fill: parent
          gradient: Gradient {
            GradientStop { position: 0; color: P.danger }
            GradientStop { position: 0.06; color: P.amber }
            GradientStop { position: 0.25; color: P.amber }
            GradientStop { position: 0.30; color: P.safe }
            GradientStop { position: 1; color: P.safe }
          }
        }
        Rectangle {
          width: parent.width; height: parent.height
          color: P.control
          opacity: 0.94
          y: -parent.height * root.ratio
          Behavior on y { NumberAnimation { duration: 80 } }
        }
        Repeater {
          model: 28
          Rectangle {
            required property int index
            y: (index + 1) * (lamps.height / 28) - 2
            width: lamps.width; height: 2
            color: P.control
          }
        }
        Rectangle {
          width: parent.width; height: 2
          y: Math.max(0, Math.min(1, -root.heldPeak / 60)) * (parent.height - height)
          color: root.clipping ? P.danger : P.metalLight
          visible: root.measured && root.heldPeak > -60
        }
      }
    }
  }
  Repeater {
    model: [0, -6, -12, -24, -36, -60]
    Text {
      required property int modelData
      x: 32
      y: 2 + (-modelData / 60) * (root.height - 16)
      text: modelData
      color: P.secondary
      font.family: P.font
      font.pixelSize: 11
    }
  }
}
