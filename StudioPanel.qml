import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Palette.js" as P

Rectangle {
  id: root
  property var snapshot: ({connected: false, channels: [], profiles: []})
  property bool stale: false
  property string errorMessage: ""
  property bool opticalOpen: false
  property string selectedProfile: ""
  readonly property bool ready: snapshot.connected === true && snapshot.synced === true && !stale
  readonly property var channels: snapshot.channels || []
  readonly property var profiles: snapshot.profiles || []
  readonly property var analogInputs: channels.filter(function(c) { return c.group === "input" && c.adjustable !== false })
  readonly property var analogOutputs: channels.filter(function(c) { return c.group === "output" && Number(c.id.replace("out", "")) <= 4 })
  readonly property var opticalChannels: channels.filter(function(c) { return c.group === "input" ? c.adjustable === false : Number(c.id.replace("out", "")) > 4 })
  signal commandRequested(var command)
  signal closeRequested()
  color: P.background
  radius: P.radius.chassis
  border.color: P.highlight; border.width: 1
  implicitWidth: P.desktopWidth
  implicitHeight: 1254
  Keys.onEscapePressed: closeRequested()

  function gainRequested(channelId, db) { if (ready) commandRequested({op: "set", channel: channelId, db: db}) }
  function chooseProfile(name) { selectedProfile = name; profilePanel.deleteCandidate = "" }
  function updateChannelModel(model, source) {
    var unchanged = model.count === source.length
    for (var i = 0; unchanged && i < source.length; i++) unchanged = model.get(i).channelData.id === source[i].id
    if (!unchanged) {
      model.clear()
      for (var j = 0; j < source.length; j++) model.append({channelData: source[j]})
    } else {
      for (var k = 0; k < source.length; k++) model.setProperty(k, "channelData", source[k])
    }
  }
  function scrollTo(item) {
    scroll.contentY = Math.max(0, Math.min(item.y, scroll.contentHeight - scroll.height))
  }
  onAnalogInputsChanged: updateChannelModel(inputModel, analogInputs)
  onAnalogOutputsChanged: updateChannelModel(outputModel, analogOutputs)
  onOpticalChannelsChanged: updateChannelModel(opticalModel, opticalChannels)
  ListModel { id: inputModel; dynamicRoles: true }
  ListModel { id: outputModel; dynamicRoles: true }
  ListModel { id: opticalModel; dynamicRoles: true }
  onProfilesChanged: {
    if (selectedProfile && profiles.indexOf(selectedProfile) < 0) chooseProfile("")
    if (!selectedProfile && snapshot.profile && profiles.indexOf(snapshot.profile) >= 0) chooseProfile(snapshot.profile)
  }

  Flickable {
    id: scroll
    objectName: "console-scroll"
    anchors.fill: parent; anchors.margins: P.spacing.large
    anchors.topMargin: 24
    contentWidth: Math.max(width, P.minimumWidth)
    contentHeight: content.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.HorizontalAndVerticalFlick
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
    ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
    Column {
      id: content
      width: scroll.contentWidth
      spacing: P.spacing.large
      TopStatusBar {
        width: parent.width
        ready: root.ready; serial: root.snapshot.serial || ""
        onCloseRequested: root.closeRequested()
        onNavigate: function(section) {
          if (section === "MONITOR") root.scrollTo(monitorSection)
          else if (section === "INPUTS") root.scrollTo(inputSection)
          else if (section === "PROFILES") root.scrollTo(bottom)
          else { root.opticalOpen = true; Qt.callLater(function() { root.scrollTo(opticalSection) }) }
        }
      }
      Rectangle {
        visible: root.errorMessage !== "" || !root.ready
        width: parent.width; height: warning.implicitHeight + P.spacing.section * 2
        color: P.control; border.color: P.amber; border.width: 1; radius: P.radius.control
        Text {
          id: warning; anchors.fill: parent; anchors.margins: P.spacing.section
          text: root.errorMessage || (root.stale ? "The control connection was interrupted. Gains are paused while we reconnect." : root.snapshot.connected ? "Waiting for fresh hardware feedback. Gains are paused." : "Connect your Babyface Pro. Saved profiles return with the device.")
          color: P.amber; font.family: P.font; font.pixelSize: 12; wrapMode: Text.WordWrap
        }
      }
      SectionPanel {
        id: monitorSection
        objectName: "monitor-section"
        width: parent.width; height: P.channelHeight + 56
        title: "MONITORING"; detail: "Analog outputs – headphones & speakers"
        RowLayout {
          anchors.fill: parent; spacing: P.spacing.large
          Repeater {
            model: outputModel
            ChannelStrip {
              required property var channelData
              channel: channelData; available: root.ready; prominent: true
              Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: 220
              onGainRequested: function(channelId, db) { root.gainRequested(channelId, db) }
            }
          }
        }
      }
      SectionPanel {
        id: inputSection
        objectName: "input-section"
        width: parent.width; height: P.channelHeight + 44
        title: "ANALOG INPUTS"; detail: "Microphone preamps & instrument / line inputs"
        RowLayout {
          anchors.fill: parent; spacing: P.spacing.large
          Repeater {
            model: inputModel
            ChannelStrip {
              required property var channelData
              channel: channelData; available: root.ready
              Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: 220
              onGainRequested: function(channelId, db) { root.gainRequested(channelId, db) }
            }
          }
        }
      }
      RowLayout {
        id: bottom
        objectName: "bottom-controls"
        width: parent.width; height: 186; spacing: P.spacing.medium
        ProfilePanel {
          id: profilePanel
          Layout.preferredWidth: parent.width * 0.31; Layout.fillHeight: true
          profiles: root.profiles; selectedProfile: root.selectedProfile; ready: root.ready
          onChoose: function(name) { root.chooseProfile(name) }
          onCommandRequested: function(command) { root.commandRequested(command) }
        }
        SectionPanel {
          Layout.fillWidth: true; Layout.fillHeight: true
          title: "DIGITAL I/O"
          RowLayout {
            anchors.fill: parent; spacing: P.spacing.large
            Column {
              Layout.fillWidth: true; spacing: P.spacing.medium
              StudioButton {
                objectName: "optical-toggle"
                text: root.opticalOpen ? "Close optical I/O" : "Optical I/O"
                implicitHeight: 42
                onClicked: { root.opticalOpen = !root.opticalOpen; if (root.opticalOpen) Qt.callLater(function() { root.scrollTo(opticalSection) }) }
              }
              Text { text: root.opticalChannels.length + " channels"; color: P.secondary; font.family: P.font; font.pixelSize: 12 }
            }
            Rectangle { width: 1; Layout.preferredHeight: 80; color: P.edge }
            Column {
              Layout.fillWidth: true; spacing: 18
              Text { text: "Feedback"; color: P.secondary; font.family: P.font; font.pixelSize: 11 }
              Text { text: root.ready ? "Live" : "Waiting"; color: root.ready ? P.connected : P.amber; font.family: P.font; font.pixelSize: 15 }
            }
            Rectangle { width: 1; Layout.preferredHeight: 80; color: P.edge }
            Column {
              Layout.fillWidth: true; spacing: 18
              Text { text: "Settings"; color: P.secondary; font.family: P.font; font.pixelSize: 11 }
              Text { text: !root.ready ? "Offline" : root.snapshot.persisted ? "Saved" : "Saving…"; color: P.text; font.family: P.font; font.pixelSize: 15 }
            }
          }
        }
        DeviceStatus { Layout.preferredWidth: parent.width * 0.28; Layout.fillHeight: true; snapshot: root.snapshot; ready: root.ready }
      }
      SectionPanel {
        id: opticalSection
        visible: root.opticalOpen
        width: parent.width
        height: opticalGrid.implicitHeight + 56
        title: "OPTICAL I/O"; detail: "Hardware meters · digital inputs remain at unity"
        GridLayout {
          id: opticalGrid
          width: parent.width
          columns: 4; columnSpacing: P.spacing.large; rowSpacing: P.spacing.large
          Repeater {
            model: root.opticalOpen ? opticalModel : null
            ChannelStrip {
              required property var channelData
              channel: channelData; available: root.ready
              Layout.fillWidth: true; Layout.preferredHeight: P.channelHeight; Layout.minimumWidth: 220
              onGainRequested: function(channelId, db) { root.gainRequested(channelId, db) }
            }
          }
        }
      }
      RowLayout {
        width: parent.width; height: 72
        RmeMark { Layout.preferredWidth: 96; Layout.preferredHeight: 24 }
        Text { text: "BABYFACE  /  CONTROL ROOM"; color: P.muted; font.family: P.font; font.pixelSize: 10; font.letterSpacing: 1.5 }
        Item { Layout.fillWidth: true }
        Text { text: root.ready && root.snapshot.persisted ? "Settings saved automatically" : "Waiting for hardware"; color: P.muted; font.family: P.font; font.pixelSize: 10 }
      }
    }
  }
}
