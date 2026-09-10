import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "kb2uka.babyface"
  ipcTarget: "kb2uka.babyface"
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  ConnectionState { id: connection }

  function send(command) {
    if (!backend.running || connection.stale) {
      connection.transportError = "The control service is reconnecting. Please try again."
      return
    }
    connection.commandStarted()
    backend.write(JSON.stringify(command) + "\n")
  }

  Process {
    id: backend
    command: ["python3", decodeURIComponent(Qt.resolvedUrl("babyface.py").toString().replace(/^file:\/\//, "")), "watch"]
    stdinEnabled: true
    running: true
    stdout: SplitParser { onRead: function(data) { connection.receive(data) } }
    stderr: SplitParser { onRead: function(data) { console.warn("Babyface control: " + data) } }
    onExited: {
      connection.transportLost()
      reconnect.restart()
    }
  }
  Timer { id: reconnect; interval: 2500; onTriggered: if (!backend.running) backend.running = true }
  Timer { interval: 250; repeat: true; running: true; onTriggered: connection.now = Date.now() }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰋋"
    active: connection.snapshot.connected === true && connection.snapshot.synced === true && !connection.stale
    onPressed: root.toggle()
  }

  KeyboardPanel {
    id: popup
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    padding: 0
    contentWidth: popup.fittedContentWidth(1240)
    contentHeight: popup.cappedContentHeight(1254)
    focusTarget: studio
    StudioPanel {
      id: studio
      anchors.fill: parent
      snapshot: connection.snapshot
      stale: connection.stale
      errorMessage: connection.errorMessage
      onCommandRequested: function(command) { root.send(command) }
      onCloseRequested: root.close()
    }
  }
}
