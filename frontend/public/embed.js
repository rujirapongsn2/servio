(function () {
  // Configuration
  const config = {
    position: document.currentScript.getAttribute('data-position') || 'bottom-right', // bottom-right, bottom-left
    serverUrl: document.currentScript.getAttribute('data-server-url') || 'http://localhost:3000',
    type: document.currentScript.getAttribute('data-type') || 'voice', // voice, chat
  };

  // Create Styles
  const style = document.createElement('style');
  style.textContent = `
    .dvoice-widget-container {
      position: fixed;
      z-index: 9999;
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      bottom: 20px;
      font-family: sans-serif;
    }
    
    .dvoice-widget-container.bottom-right {
      right: 20px;
      align-items: flex-end;
    }
    
    .dvoice-widget-container.bottom-left {
      left: 20px;
      align-items: flex-start;
    }

    .dvoice-widget-frame {
      width: 380px;
      height: 580px;
      border: none;
      border-radius: 16px;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
      margin-bottom: 16px;
      background: white;
      transition: opacity 0.3s ease, transform 0.3s ease;
      opacity: 0;
      transform: translateY(20px);
      pointer-events: none;
      position: absolute;
      bottom: 70px;
    }
    
    .dvoice-widget-frame.visible {
      opacity: 1;
      transform: translateY(0);
      pointer-events: all;
    }

    .dvoice-widget-button {
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
      box-shadow: 0 4px 16px rgba(37, 99, 235, 0.4);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.3s ease;
      border: none;
      outline: none;
    }

    .dvoice-widget-button:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5);
    }

    .dvoice-widget-icon {
      width: 32px;
      height: 32px;
      fill: white;
      transition: transform 0.3s ease;
    }
    
    .dvoice-widget-button.open .dvoice-widget-icon {
      transform: rotate(45deg);
    }
  `;
  document.head.appendChild(style);

  // Create Container
  const container = document.createElement('div');
  container.className = `dvoice-widget-container ${config.position}`;

  // Create Iframe
  const iframe = document.createElement('iframe');
  iframe.className = 'dvoice-widget-frame';
  iframe.src = `${config.serverUrl}/widget?type=${config.type}`;
  // Only request microphone permission for voice mode
  if (config.type === 'voice') {
    iframe.allow = "microphone";
  }

  // Create Button
  const button = document.createElement('button');
  button.className = 'dvoice-widget-button';
  button.innerHTML = `
    <svg class="dvoice-widget-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/>
    </svg>
  `;

  // Toggle Logic
  let isOpen = false;
  button.addEventListener('click', () => {
    isOpen = !isOpen;
    if (isOpen) {
      iframe.classList.add('visible');
      button.classList.add('open');
      // Change icon to close X
      button.innerHTML = `
        <svg class="dvoice-widget-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
        </svg>
      `;
    } else {
      iframe.classList.remove('visible');
      button.classList.remove('open');
      // Change icon back to chat bubble
      button.innerHTML = `
        <svg class="dvoice-widget-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/>
        </svg>
      `;
    }
  });

  // Assemble
  container.appendChild(iframe);
  container.appendChild(button);
  document.body.appendChild(container);

})();
