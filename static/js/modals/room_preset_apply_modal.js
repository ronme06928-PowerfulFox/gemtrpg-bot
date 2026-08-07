(function (global) {
  'use strict';

  function openRoomPresetApplyModal() {
    if (typeof global.openPresetDeploymentBrowser !== 'function') {
      console.error('[RoomPresetApply] 配置画面が読み込まれていません。');
      global.alert('プリセット配置画面を読み込めませんでした。画面を再読み込みしてください。');
      return;
    }
    const room = String(
      (typeof currentRoomName !== 'undefined' ? currentRoomName : '')
      || global.currentRoomName
      || '',
    ).trim();
    if (!room) {
      global.alert('ルーム情報を取得できませんでした。');
      return;
    }
    global.openPresetDeploymentBrowser({ room, targetMode: 'normal' });
  }

  global.openRoomPresetApplyModal = openRoomPresetApplyModal;
})(window);
