import QtQuick
import QtQuick.Layouts
import "Palette.js" as P

Rectangle {
  id: root
  property bool ready: false
  property string serial: ""
  property string selected: "MONITOR"
  signal navigate(string section)
  signal closeRequested()
  implicitHeight: 84
  radius: P.radius.control
  border.color: P.border; border.width: 1
  gradient: Gradient { GradientStop { position: 0; color: P.elevated } GradientStop { position: 1; color: P.background } }
  Rectangle { anchors.fill: parent; anchors.margins: 2; color: "transparent"; border.color: P.highlight; border.width: 1; radius: 3; opacity: 0.5 }
  RowLayout {
    anchors.fill: parent; anchors.margins: P.spacing.large
    spacing: P.spacing.large
    RmeMark { Layout.preferredWidth: root.width < 1100 ? 110 : 150; Layout.preferredHeight: 40 }
    Rectangle { width: 1; Layout.preferredHeight: 48; color: P.highlight }
    Column {
      spacing: 3
      Text { text: "Babyface Pro"; color: P.text; font.family: P.font; font.pixelSize: root.width < 1100 ? 25 : 30; font.weight: Font.DemiBold }
      Text { text: "C O N T R O L  R O O M"; color: P.secondary; font.family: P.font; font.pixelSize: 10; font.letterSpacing: 1 }
    }
    Item { Layout.fillWidth: true }
    Repeater {
      model: ["MONITOR", "INPUTS", "OPTICAL", "PROFILES"]
      Item {
        required property string modelData
        Layout.preferredWidth: root.width < 1100 ? 64 : 84; Layout.fillHeight: true
        StudioButton {
          anchors.fill: parent
          text: parent.modelData
          background: Item {}
          onClicked: { root.selected = parent.modelData; root.navigate(parent.modelData) }
        }
        Rectangle { anchors { left: parent.left; right: parent.right; bottom: parent.bottom } height: 3; radius: 1; color: P.accent; visible: root.selected === parent.modelData }
      }
    }
    Rectangle {
      Layout.preferredWidth: root.width < 1100 ? 180 : 210; Layout.fillHeight: true
      radius: P.radius.control; color: P.control; border.color: P.highlight; border.width: 1
      Column {
        anchors.centerIn: parent; spacing: 9
        Row {
          spacing: 10
          Rectangle { width: 9; height: 9; radius: 5; anchors.verticalCenter: parent.verticalCenter; color: root.ready ? P.connected : P.amber }
          Text { text: root.ready ? "CONNECTED" : "WAITING FOR DEVICE"; color: root.ready ? P.connected : P.amber; font.family: P.font; font.pixelSize: 12 }
        }
        Text { text: "Babyface Pro" + (root.serial ? " (S/N " + root.serial + ")" : ""); color: P.secondary; font.family: P.font; font.pixelSize: 10 }
      }
    }
    StudioButton { text: "×"; implicitWidth: 36; implicitHeight: 54; Accessible.name: "Close Babyface panel"; onClicked: root.closeRequested() }
  }
}
