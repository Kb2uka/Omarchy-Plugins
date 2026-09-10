import QtQuick
import QtQuick.Controls
import "Palette.js" as P

Dial {
  id: root
  property real sweepAngle: 270
  implicitWidth: 118
  implicitHeight: 118
  inputMode: Dial.Vertical
  wrap: false
  snapMode: Dial.SnapAlways
  hoverEnabled: true
  opacity: enabled ? 1 : 0.42
  background: Canvas {
    id: face
    anchors.fill: parent
    onPaint: {
      var ctx = getContext("2d")
      ctx.reset()
      var cx=width/2, cy=height/2, r=Math.min(width,height)/2-3
      function disk(radius, top, bottom) {
        var g=ctx.createLinearGradient(cx-radius,cy-radius,cx+radius,cy+radius)
        g.addColorStop(0,top);g.addColorStop(1,bottom)
        ctx.beginPath();ctx.arc(cx,cy,radius,0,Math.PI*2);ctx.fillStyle=g;ctx.fill()
      }
      disk(r,P.control,P.border)
      ctx.beginPath();ctx.arc(cx,cy,r-1,0,Math.PI*2);ctx.strokeStyle=P.highlight;ctx.lineWidth=1;ctx.stroke()
      ctx.beginPath();ctx.arc(cx,cy,r-5,Math.PI*0.75,Math.PI*(0.75+root.sweepAngle/180))
      ctx.strokeStyle=P.edge;ctx.lineWidth=4;ctx.stroke()
      ctx.beginPath();ctx.arc(cx,cy,r-5,Math.PI*0.75,Math.PI*(0.75+root.position*root.sweepAngle/180))
      ctx.strokeStyle=P.accent;ctx.lineWidth=3;ctx.stroke()
      ctx.beginPath();ctx.arc(cx,cy,r-6,Math.PI*0.75,Math.PI*(0.75+root.position*root.sweepAngle/180))
      ctx.strokeStyle=P.accentActive;ctx.lineWidth=1;ctx.stroke()
      disk(r-11,P.highlight,P.border)
      disk(r-13,P.elevated,P.control)
      var shine=ctx.createRadialGradient(cx-r*.28,cy-r*.3,1,cx,cy,r-14)
      shine.addColorStop(0,P.metalDark);shine.addColorStop(.52,P.elevated);shine.addColorStop(1,P.control)
      ctx.beginPath();ctx.arc(cx,cy,r-14,0,Math.PI*2);ctx.fillStyle=shine;ctx.fill()
      ctx.beginPath();ctx.arc(cx,cy,r-12,Math.PI*1.03,Math.PI*1.94)
      ctx.strokeStyle=P.highlight;ctx.lineWidth=1;ctx.stroke()
    }
    Connections { target: root; function onPositionChanged() { face.requestPaint() } }
  }
  handle: Item {
    anchors.fill: parent
    rotation: -135 + root.position * root.sweepAngle
    Rectangle {
      anchors.horizontalCenter: parent.horizontalCenter
      y: 15
      width: 4; height: 27
      color: P.metalLight
      border.color: P.text; border.width: 1
    }
  }
  Rectangle {
    anchors.fill: parent; radius: width/2
    color: "transparent"; border.width: 1; border.color: P.accent
    visible: root.activeFocus
  }
}
