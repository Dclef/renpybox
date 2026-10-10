import { Sidecar } from '../main/sidecar.js';
import { stdioConsole } from '../main/stdio-console.js';

const sidecar = new Sidecar({ onLog: stdioConsole.log });
const stop = async () => {
  await sidecar.stop();
  process.exit(0);
};
process.on('SIGINT', stop);
process.on('SIGTERM', stop);

try {
  const info = await sidecar.start();
  stdioConsole.log(`[sidecar] 后端已就绪，Python ${info.python_version}，pid=${info.pid}`);
} catch (error) {
  stdioConsole.error(error.message);
  await sidecar.stop();
  process.exit(1);
}
