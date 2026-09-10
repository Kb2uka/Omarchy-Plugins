import QtQuick
import QtQuick.Controls
import "Palette.js" as P

Slider {
  id: root
  implicitHeight: 32
  hoverEnabled: true
  snapMode: Slider.SnapAlways
  live: true
  opacity: enabled ? 1 : 0.4
  background: Rectangle {
    x: root.leftPadding
    y: root.topPadding + root.availableHeight / 2 - height / 2
    width: root.availableWidth
    height: 7
    radius: 2
    color: P.control
    border.width: 1
    border.color: P.highlight
    Rectangle {
      x: 1; y: 1
      width: Math.max(0, root.visualPosition * (parent.width - 2))
      height: 4
      radius: 1
      gradient: Gradient {
        GradientStop { position: 0; color: P.accentActive }
        GradientStop { position: 1; color: P.accent }
      }
    }
  }
  handle: Rectangle {
    x: root.leftPadding + root.visualPosition * (root.availableWidth - width)
    y: root.topPadding + root.availableHeight / 2 - height / 2
    width: 19; height: 33
    radius: 3
    border.width: 1
    border.color: P.border
    gradient: Gradient {
      orientation: Gradient.Horizontal
      GradientStop { position: 0; color: P.metalLight }
      GradientStop { position: 0.14; color: P.metalMid }
      GradientStop { position: 0.8; color: P.metalMid }
      GradientStop { position: 1; color: P.metalDark }
    }
    Rectangle {
      anchors.fill: parent; anchors.margins: 2
      color: "transparent"; radius: 1
      border.color: root.activeFocus ? P.accent : P.metalLight
      border.width: 1
    }
  }
}
