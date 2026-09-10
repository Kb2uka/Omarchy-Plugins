import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Palette.js" as P

SectionPanel {
  id: root
  property var profiles: []
  property string selectedProfile: ""
  property bool ready: false
  property string deleteCandidate: ""
  signal choose(string name)
  signal commandRequested(var command)
  title: "PROFILES"
  Column {
    anchors.fill: parent
    spacing: P.spacing.small
    ComboBox {
      id: selector
      objectName: "profile-selector"
      width: parent.width; height: 37
      model: root.profiles
      currentIndex: root.profiles.indexOf(root.selectedProfile)
      displayText: currentIndex < 0 ? "Select saved profile" : root.selectedProfile
      onActivated: root.choose(currentText)
      contentItem: Text { leftPadding: 12; text: selector.displayText; color: P.text; font.family: P.font; font.pixelSize: 15; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
      background: Rectangle { color: P.surface; radius: P.radius.control; border.color: selector.activeFocus ? P.accent : P.highlight; border.width: 1 }
      delegate: ItemDelegate {
        required property string modelData
        required property int index
        width: selector.width
        highlighted: selector.highlightedIndex === index
        contentItem: Text { text: modelData; color: P.text; font.family: P.font; font.pixelSize: 13 }
        background: Rectangle { color: parent.highlighted ? P.accentDark : P.surface }
      }
      popup: Popup {
        y: selector.height; width: selector.width; padding: 1
        implicitHeight: Math.min(240, profileList.contentHeight + 2)
        background: Rectangle { color: P.surface; border.color: P.highlight; radius: P.radius.control }
        contentItem: ListView { id: profileList; clip: true; implicitHeight: contentHeight; model: selector.popup.visible ? selector.delegateModel : null; currentIndex: selector.highlightedIndex; ScrollIndicator.vertical: ScrollIndicator {} }
      }
    }
    TextField {
      id: name
      objectName: "profile-name"
      width: parent.width; height: 29
      maximumLength: 48
      placeholderText: "Name this setup to save…"
      placeholderTextColor: P.muted; color: P.text
      font.family: P.font; font.pixelSize: 12
      leftPadding: 10; selectByMouse: true
      Accessible.name: "New profile name"
      background: Rectangle { color: P.control; radius: P.radius.control; border.color: name.activeFocus ? P.accent : P.edge; border.width: 1 }
    }
    RowLayout {
      width: parent.width; spacing: P.spacing.medium
      StudioButton {
        objectName: "save-profile"; text: "Save"; Layout.fillWidth: true; implicitHeight: 38
        enabled: root.ready && name.text.trim() !== ""
        onClicked: { root.commandRequested({op: "save_profile", name: name.text.trim()}); root.choose(name.text.trim()) }
      }
      StudioButton {
        objectName: "apply-profile"; text: "Apply"; primary: true; Layout.fillWidth: true; implicitHeight: 38
        enabled: root.ready && root.profiles.indexOf(root.selectedProfile) >= 0
        onClicked: root.commandRequested({op: "load_profile", name: root.selectedProfile})
      }
      StudioButton {
        objectName: "delete-profile"; text: root.deleteCandidate ? "Confirm" : "Delete"; destructive: true; Layout.fillWidth: true; implicitHeight: 38
        enabled: root.ready && root.profiles.indexOf(root.selectedProfile) >= 0
        onClicked: {
          if (root.deleteCandidate === root.selectedProfile) { root.commandRequested({op: "delete_profile", name: root.selectedProfile}); root.deleteCandidate = "" }
          else root.deleteCandidate = root.selectedProfile
        }
      }
    }
  }
}
