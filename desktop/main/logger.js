import { appendFileSync, mkdirSync, existsSync, statSync, renameSync, rmSync } from 'node:fs';
import path from 'node:path';
import { inspect, stripVTControlCharacters } from 'node:util';
import { stdioConsole } from './stdio-console.js';

/** Concise console output; complete diagnostics remain in the local log. */
export function createLogger(logDir, { consoleOutput = true } = {}) {
  mkdirSync(logDir, { recursive: true });
  const logPath = path.join(logDir, 'desktop.log');
  if (existsSync(logPath) && statSync(logPath).size > 5 * 1024 * 1024) {
    const previous = `${logPath}.1`;
    if (existsSync(previous)) rmSync(previous);
    renameSync(logPath, previous);
  }
  const format = value => value instanceof Error
    ? value.stack || value.message
    : typeof value === 'string' ? value : inspect(value, { depth: 4 });
  function write(level, args) {
    const message = stripVTControlCharacters(args.map(format).join(' '));
    appendFileSync(logPath, `${new Date().toISOString()} [${level}] ${message}` + String.fromCharCode(10), 'utf8');
    if (consoleOutput && level !== 'DEBUG') {
      const firstLine = message.split(/\r?\n/, 1)[0];
      const output = level === 'ERROR' ? stdioConsole.error : stdioConsole.log;
      output(`[RenpyBox] ${firstLine}`);
    }
  }
  const log = (...args) => write('INFO', args);
  log.path = logPath;
  for (const level of ['info', 'warn', 'error', 'debug']) {
    log[level] = (...args) => write(level.toUpperCase(), args);
  }
  return log;
}
