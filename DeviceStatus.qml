import QtQuick
import QtQuick.Layouts
import "Palette.js" as P

SectionPanel {
  id: root
  property var snapshot: ({})
  property bool ready: false
  title: "DEVICE"
  RowLayout {
    anchors.fill: parent; spacing: P.spacing.section
    Canvas {
      Layout.preferredWidth: 116; Layout.preferredHeight: 116
      onPaint: {
        var c=getContext("2d");c.reset()
        var g=c.createLinearGradient(15,15,92,108);g.addColorStop(0,P.metalLight);g.addColorStop(.48,P.metalMid);g.addColorStop(1,P.metalDark)
        c.beginPath();c.moveTo(38,7);c.lineTo(112,24);c.lineTo(85,106);c.lineTo(8,83);c.closePath();c.fillStyle=g;c.fill();c.strokeStyle=P.highlight;c.lineWidth=1;c.stroke()
        c.beginPath();c.moveTo(8,83);c.lineTo(85,106);c.lineTo(85,114);c.lineTo(8,91);c.closePath();c.fillStyle=P.metalDark;c.fill()
        c.beginPath();c.ellipse(66,57,22,18);c.fillStyle=P.control;c.fill();c.strokeStyle=P.metalLight;c.stroke()
        c.beginPath();c.ellipse(66,57,16,13);c.fillStyle=P.elevated;c.fill();c.strokeStyle=P.highlight;c.stroke()
        c.fillStyle=P.text;c.font='8px sans-serif';c.fillText('RME',51,29)
        c.fillStyle=P.control;c.fillRect(29,71,14,6);c.fillRect(67,84,11,6)
        c.fillStyle=P.accent;c.fillRect(35,43,3,10)
      }
    }
    Column {
      Layout.fillWidth: true; spacing: P.spacing.medium
      Text { text: "RME Babyface Pro"; color: P.text; font.family: P.font; font.pixelSize: 15 }
      Text { text: root.snapshot.serial ? "S/N " + root.snapshot.serial : "No device connected"; color: P.secondary; font.family: P.font; font.pixelSize: 12 }
      Text { text: root.ready ? "Class-compliant USB" : "Waiting for feedback"; color: P.secondary; font.family: P.font; font.pixelSize: 12 }
      Row {
        spacing: P.spacing.medium
        Rectangle { width: 6; height: 6; radius: 3; anchors.verticalCenter: parent.verticalCenter; color: root.ready ? P.connected : P.amber }
        Text { text: root.ready ? "Hardware connected" : "Offline"; color: P.muted; font.family: P.font; font.pixelSize: 11 }
      }
    }
  }
}
