import QtQuick
import QtQuick.Controls
import "Palette.js" as P

Button {
  id: root
  property bool primary: false
  property bool destructive: false
  implicitHeight: 40
  implicitWidth: Math.max(54, contentItem.implicitWidth + P.spacing.section * 2)
  hoverEnabled: true
  Accessible.name: text
  contentItem: Text {
    text: root.text
    font.family: P.font
    font.pixelSize: 13
    color: !root.enabled ? P.muted : root.destructive && root.hovered ? P.danger : P.text
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    elide: Text.ElideRight
  }
  background: Rectangle {
    radius: P.radius.control
    border.width: 1
    border.color: root.activeFocus || root.primary ? P.accent : P.border
    opacity: root.enabled ? 1 : 0.45
    gradient: Gradient {
      GradientStop { position: 0; color: root.primary ? P.accentDark : root.hovered ? P.edge : P.elevated }
      GradientStop { position: 0.18; color: root.primary ? P.accentDark : P.surface }
      GradientStop { position: 1; color: root.down ? P.control : P.background }
    }
    Rectangle {
      anchors.fill: parent
      anchors.margins: 2
      color: "transparent"
      radius: 2
      border.width: 1
      border.color: root.primary ? P.accent : P.highlight
      opacity: root.primary ? 0.7 : 0.42
    }
  }
}
