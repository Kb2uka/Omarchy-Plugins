import QtQuick
import "Palette.js" as P

Rectangle {
  id: root
  property string title: ""
  property string detail: ""
  property int inset: P.spacing.large
  default property alias content: holder.data
  radius: P.radius.panel
  border.width: 1
  border.color: P.border
  gradient: Gradient {
    GradientStop { position: 0; color: P.elevated }
    GradientStop { position: 0.06; color: P.surface }
    GradientStop { position: 1; color: P.background }
  }
  Rectangle {
    anchors.fill: parent
    anchors.margins: 2
    radius: parent.radius - 1
    color: "transparent"
    border.width: 1
    border.color: P.edge
  }
  Text {
    x: root.inset + 8; y: 16
    text: root.title
    color: P.text
    font.family: P.font
    font.pixelSize: 13
    font.letterSpacing: 2.5
  }
  Text {
    anchors.right: parent.right
    anchors.rightMargin: root.inset + 8
    y: 16
    text: root.detail
    color: P.secondary
    font.family: P.font
    font.pixelSize: 13
    visible: root.width > 650
  }
  Item {
    id: holder
    anchors { left: parent.left; right: parent.right; top: parent.top; bottom: parent.bottom }
    anchors.leftMargin: root.inset
    anchors.rightMargin: root.inset
    anchors.topMargin: 44
    anchors.bottomMargin: root.inset
  }
}
