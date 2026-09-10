import QtQuick
import "Palette.js" as P

Canvas {
  implicitWidth: 150
  implicitHeight: 40
  onPaint: {
    var c=getContext("2d");c.reset();c.scale(width/176,height/44)
    var metal=c.createLinearGradient(0,5,0,40)
    metal.addColorStop(0,P.metalLight);metal.addColorStop(.45,P.metalMid);metal.addColorStop(1,P.metalDark)
    c.lineJoin="miter";c.lineWidth=1.2;c.strokeStyle=P.metalLight;c.fillStyle=metal
    function outline(points) {
      c.beginPath();c.moveTo(points[0][0],points[0][1])
      for(var i=1;i<points.length;i++)c.lineTo(points[i][0],points[i][1])
      c.closePath();c.fill();c.stroke()
    }
    outline([[4,38],[4,6],[53,6],[58,11],[58,21],[52,26],[61,38],[45,38],[34,25],[16,25],[16,38]])
    c.fillStyle=P.surface;c.fillRect(16,13,30,6);c.strokeRect(16,13,30,6);c.fillStyle=metal
    outline([[67,38],[67,6],[85,6],[91,23],[97,6],[115,6],[115,38],[104,38],[104,18],[96,38],[86,38],[78,18],[78,38]])
    outline([[122,6],[172,6],[172,14],[135,14],[135,18],[167,18],[167,26],[135,26],[135,30],[172,30],[172,38],[122,38]])
  }
}
