// PWA Service Worker 注册
export function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js')
        .then((registration) => {
          console.log('SW registered:', registration);
        })
        .catch((error) => {
          console.log('SW registration failed:', error);
        });
    });
  }
}

// 检查是否安装为 PWA
export function isPWA(): boolean {
  return window.matchMedia('(display-mode: standalone)').matches;
}

// 提示安装 PWA
export function promptInstall() {
  // 需要监听 beforeinstallprompt 事件
  // 这里只是示例
  console.log('PWA install prompt');
}
