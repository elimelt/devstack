import FrameManager from './frame-manager.js';
import StorageManager from './storage-manager.js';
import KeyboardManager from './keyboard-manager.js';
import UIManager from './ui-manager.js';

class App {
  constructor() {
    this.frameManager = new FrameManager();
    this.storageManager = new StorageManager();
    this.keyboardManager = new KeyboardManager();
    this.uiManager = new UIManager(this.frameManager, this.storageManager);
  }

  init() {
    this.uiManager.init();
    this.setupKeyboardShortcuts();
    this.setupClearButton();
    this.uiManager.loadState();
  }

  setupKeyboardShortcuts() {
    this.keyboardManager.init();
    
    this.keyboardManager.register('ctrl+n', () => {
      this.uiManager.focusNext();
    });
    
    this.keyboardManager.register('ctrl+p', () => {
      this.uiManager.focusPrev();
    });
    
    this.keyboardManager.register('ctrl+w', () => {
      this.uiManager.removeActive();
    });
    
    this.keyboardManager.register('ctrl+shift+c', () => {
      this.uiManager.clearAll();
    });
  }

  setupClearButton() {
    const clearBtn = document.getElementById('clear-all');
    clearBtn.addEventListener('click', () => {
      this.uiManager.clearAll();
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const app = new App();
  app.init();
});

