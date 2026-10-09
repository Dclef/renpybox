import { Sidecar } from '../main/sidecar.js';

const sidecar = new Sidecar({ onLog: console.log });
const stop = async () => {
  await sidecar.stop();
  process.exit(0);
};
process.on('SIGINT', stop);
process.on('SIGTERM', stop);

try {
  const info = await sidecar.start();
  console.log(`[sidecar] 后端已就绪，Python ${info.python_version}，pid=${info.pid}`);
} catch (error) {
  console.error(error.message);
  await sidecar.stop();
  process.exit(1);
}
