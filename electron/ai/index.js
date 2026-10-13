// Cửa vào duy nhất mà electron/src/main.ts nạp (dynamic import — thư mục này là ESM).
export * from './accounts.js';
export { startLocalServer, stopLocalServer } from './localServer.js';
