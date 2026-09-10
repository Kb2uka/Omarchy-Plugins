import QtQuick
import QtTest
import "../.." as Studio

Item {
  id: stage
  width: 1240
  height: 1254
  Studio.StudioPanel { id: panel; anchors.fill: parent }
  Studio.ConnectionState { id: connection }
  Studio.LevelMeter { id: meter; visible: false }
  SignalSpy { id: commands; target: panel; signalName: "commandRequested" }
  TestCase {
    name: "BabyfacePanel"
    when: windowShown

    function sample() {
      var channels = []
      for (var i = 1; i <= 12; i++) {
        channels.push({id: i <= 2 ? "mic" + i : i <= 4 ? "line" + i : "in" + i,
          label: i <= 2 ? "Microphone " + i : i <= 4 ? "Line / instrument " + i : "Digital input " + (i - 4),
          port: i <= 4 ? "AN " + i : "ADAT " + (i - 4), group: "input", adjustable: i <= 4,
          min: 0, max: i <= 2 ? 65 : 9, step: 1, db: i <= 2 ? 40 : 0,
          peak: i <= 2 ? -18 : null, readback: true})
        channels.push({id: "out" + i, label: i <= 2 ? "Monitor " + (i === 1 ? "left" : "right") : i <= 4 ? "Headphone " + (i === 3 ? "left" : "right") : "Optical out " + (i - 4),
          port: i <= 2 ? "AN " + i : i <= 4 ? "PH " + i : "ADAT " + (i - 4), group: "output", adjustable: true,
          min: -65, max: 6, step: 0.5, db: i <= 2 ? -20 : i <= 4 ? 5 : 0, peak: i <= 4 ? -12 : null, readback: i <= 6})
      }
      return {connected: true, synced: true, persisted: true, serial: "73084045", device: "Babyface Pro", channels: channels, profiles: ["Evening listening", "Broadcast voice"], profile: "Evening listening"}
    }
    function init() {
      stage.width = 1240
      panel.snapshot = sample()
      panel.stale = false
      panel.errorMessage = ""
      panel.opticalOpen = false
      panel.chooseProfile("")
      findChild(panel, "profile-name").text = ""
      connection.commandError = ""
      connection.transportError = ""
      connection.lastUpdate = 0
      meter.available = true
      meter.peak = null
      commands.clear()
      wait(40)
    }
    function test_hardwareFeedbackMustBeFresh() {
      var state = sample()
      state.synced = false
      panel.snapshot = state
      compare(panel.ready, false)
      verify(!findChild(findChild(panel, "channel-out3"), "gain-slider").enabled)
    }
    function test_profileNameMatchesBackendLimit() {
      compare(findChild(panel, "profile-name").maximumLength, 48)
    }
    function test_connectionErrorsSurviveSnapshots() {
      connection.receive(JSON.stringify(sample()))
      connection.receive(JSON.stringify({error: "Profile could not be saved"}))
      for (var i = 0; i < 10; i++) connection.receive(JSON.stringify(sample()))
      compare(connection.errorMessage, "Profile could not be saved")
      connection.commandStarted()
      compare(connection.errorMessage, "")
      connection.receive(JSON.stringify({error: "Second failure"}))
      connection.receive(JSON.stringify({ok: true}))
      compare(connection.errorMessage, "")
    }
    function test_connectionExitDisablesImmediately() {
      connection.receive(JSON.stringify(sample()))
      connection.transportLost()
      compare(connection.snapshot.connected, false)
      compare(connection.snapshot.persisted, false)
      verify(connection.errorMessage !== "")
    }
    function test_connectionBecomesStaleAtOneSecond() {
      connection.receive(JSON.stringify(sample()))
      connection.now = connection.lastUpdate + 999
      compare(connection.stale, false)
      connection.now = connection.lastUpdate + 1000
      compare(connection.stale, true)
    }
    function test_snapshotDoesNotWriteGains() {
      compare(panel.analogInputs.length, 4)
      compare(panel.analogOutputs.length, 4)
      compare(panel.opticalChannels.length, 16)
      compare(commands.count, 0)
      panel.snapshot = sample()
      wait(40)
      compare(commands.count, 0)
    }
    function test_gainCommand() {
      var card = findChild(panel, "channel-mic1")
      verify(card !== null)
      card.setGain(41)
      compare(commands.count, 1)
      compare(commands.signalArguments[0][0].channel, "mic1")
      compare(commands.signalArguments[0][0].db, 41)
      card.setGain(100)
      compare(commands.signalArguments[1][0].db, 65)
      card.setGain(-10)
      compare(commands.signalArguments[2][0].db, 0)
    }
    function test_snapshotKeepsActiveControls() {
      var before = findChild(panel, "channel-mic1")
      var next = sample()
      next.channels[0].db = 42
      panel.snapshot = next
      wait(20)
      compare(findChild(panel, "channel-mic1"), before)
      compare(findChild(before, "gain-slider").value, 42)
      compare(commands.count, 0)
    }
    function test_mutePreservesNull() {
      var card = findChild(panel, "channel-out3")
      findChild(card, "mute-output").clicked()
      compare(commands.count, 1)
      compare(commands.signalArguments[0][0].channel, "out3")
      compare(commands.signalArguments[0][0].db, null)
    }
    function test_pointerGestureCoalescesAndCommitsRelease() {
      var slider = findChild(findChild(panel, "channel-mic1"), "gain-slider")
      mousePress(slider, slider.width * 0.6, slider.height / 2)
      mouseMove(slider, slider.width * 0.7, slider.height / 2)
      mouseMove(slider, slider.width * 0.8, slider.height / 2)
      compare(commands.count, 0)
      wait(100)
      compare(commands.count, 1)
      mouseMove(slider, slider.width * 0.75, slider.height / 2)
      mouseMove(slider, slider.width * 0.70, slider.height / 2)
      wait(100)
      compare(commands.count, 2)
      mouseRelease(slider, slider.width * 0.70, slider.height / 2)
      compare(commands.count, 3)
      compare(commands.signalArguments[2][0].db, slider.value)
      var next = sample()
      next.channels[0].db = 43
      panel.snapshot = next
      wait(20)
      compare(slider.value, 43)
    }
    function test_keyboardGain() {
      var card = findChild(panel, "channel-mic1")
      var slider = findChild(card, "gain-slider")
      slider.forceActiveFocus()
      keyClick(Qt.Key_Right)
      compare(commands.count, 1)
      compare(commands.signalArguments[0][0].db, 41)
    }
    function test_staleBlocksChanges() {
      panel.stale = true
      wait(10)
      var card = findChild(panel, "channel-mic1")
      card.setGain(45)
      compare(commands.count, 0)
      compare(findChild(card, "gain-slider").enabled, false)
    }
    function test_digitalInputFixed() {
      panel.opticalOpen = true
      wait(20)
      var card = findChild(panel, "channel-in5")
      verify(card !== null)
      compare(card.adjustable, false)
      card.setGain(4)
      compare(commands.count, 0)
    }
    function test_profileCommands() {
      panel.chooseProfile("Broadcast voice")
      findChild(panel, "apply-profile").clicked()
      compare(commands.signalArguments[0][0].op, "load_profile")
      compare(commands.signalArguments[0][0].name, "Broadcast voice")
      var remove = findChild(panel, "delete-profile")
      remove.clicked()
      compare(commands.count, 1)
      remove.clicked()
      compare(commands.signalArguments[1][0].op, "delete_profile")
      var name = findChild(panel, "profile-name")
      name.text = "Voice • café"
      findChild(panel, "save-profile").clicked()
      compare(commands.signalArguments[2][0].name, "Voice • café")
    }
    function test_meterUsesOnlyMeasuredValues() {
      var card = findChild(panel, "channel-mic1")
      verify(card.measured)
      compare(card.meterRatio, 0.7)
      var unmeasured = findChild(panel, "channel-line3")
      compare(unmeasured.measured, false)
      compare(unmeasured.meterRatio, 0)
      panel.stale = true
      wait(10)
      compare(card.meterRatio, 0)
    }
    function test_rotaryKeyboardAndHardwareFeedback() {
      var card = findChild(panel, "channel-mic1")
      var knob = findChild(card, "gain-knob")
      knob.forceActiveFocus()
      keyClick(Qt.Key_Right)
      compare(commands.count, 1)
      compare(commands.signalArguments[0][0].channel, "mic1")
      compare(commands.signalArguments[0][0].db, 41)
      var next = sample()
      next.channels[0].db = 43
      panel.snapshot = next
      wait(20)
      compare(knob.value, 43)
      compare(findChild(card, "gain-slider").value, 43)
      compare(commands.count, 1)
    }
    function test_rotaryDragCoalescesAndStaleCancels() {
      var knob = findChild(findChild(panel, "channel-mic1"), "gain-knob")
      mousePress(knob, knob.width / 2, knob.height / 2)
      mouseMove(knob, knob.width / 2, knob.height / 2 - 20)
      mouseMove(knob, knob.width / 2, knob.height / 2 - 30)
      compare(commands.count, 0)
      wait(100)
      compare(commands.count, 1)
      panel.stale = true
      mouseRelease(knob, knob.width / 2, knob.height / 2 - 30)
      compare(commands.count, 1)
      verify(!knob.enabled)
    }
    function test_narrowViewportKeepsStripsAlignedAndScrolls() {
      stage.width = 520
      wait(30)
      var scroll = findChild(panel, "console-scroll")
      verify(scroll.contentWidth > scroll.width)
      var first = findChild(panel, "channel-out1")
      var last = findChild(panel, "channel-out4")
      compare(first.y, last.y)
      compare(first.height, last.height)
      verify(last.x > first.x)
      var controls = findChild(first, "channel-content")
      for (var i = 0; i < controls.children.length; i++) {
        var child = controls.children[i]
        if (child.visible) verify(child.y + child.height <= controls.height + 1, "Channel content overflows")
      }
    }
    function test_meterPeakHoldAndClipAreMeasured() {
      meter.peak = -12
      compare(meter.ratio, 0.8)
      compare(meter.clipping, false)
      meter.peak = 0.2
      compare(meter.clipping, true)
      meter.peak = -20
      compare(meter.clipping, true)
      wait(1200)
      compare(meter.clipping, false)
      meter.available = false
      compare(meter.ratio, 0)
      compare(meter.clipping, false)
    }
    function test_profileChoiceSurvivesLiveSnapshots() {
      var selector = findChild(panel, "profile-selector")
      selector.popup.open()
      wait(50)
      var list = selector.popup.contentItem
      var row = list.itemAtIndex(1)
      verify(row !== null)
      mousePress(row, row.width / 2, row.height / 2)
      panel.snapshot = sample()
      wait(40)
      tryVerify(function() { return list.itemAtIndex(1) !== null }, 500)
      row = list.itemAtIndex(1)
      mouseRelease(row, row.width / 2, row.height / 2)
      compare(panel.selectedProfile, "Broadcast voice")
      selector.popup.close()
    }
    function test_zCapture() {
      panel.chooseProfile("Evening listening")
      wait(180)
      grabImage(panel).save(Qt.resolvedUrl("../../.artifacts/feat_babyface_panel/panel-fixture.png").toString().replace("file://", ""))
      stage.width = 520
      compare(panel.width, 520)
      wait(80)
      grabImage(panel).save(Qt.resolvedUrl("../../.artifacts/feat_babyface_panel/panel-narrow-fixture.png").toString().replace("file://", ""))
    }
  }
}
