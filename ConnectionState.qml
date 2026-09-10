import QtQuick

QtObject {
  id: root
  property var snapshot: ({connected: false, persisted: false, channels: [], profiles: []})
  property string commandError: ""
  property string transportError: ""
  property double lastUpdate: 0
  property double now: Date.now()
  readonly property bool stale: lastUpdate > 0 && now - lastUpdate >= 1000
  readonly property string errorMessage: commandError || transportError || snapshot.error || ""

  function receive(data) {
    try {
      var message = JSON.parse(data)
      if (message.connected !== undefined) {
        snapshot = message
        lastUpdate = Date.now()
        now = lastUpdate
        transportError = ""
      } else if (message.error) commandError = String(message.error)
      else if (message.ok === true) commandError = ""
    } catch (error) {
      transportError = "The control service sent an unreadable response."
    }
  }

  function commandStarted() { commandError = "" }

  function transportLost() {
    snapshot = Object.assign({}, snapshot, {connected: false, persisted: false})
    transportError = "The control connection stopped. Reconnecting…"
  }
}
