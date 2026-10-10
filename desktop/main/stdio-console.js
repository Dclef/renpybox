function rethrowUnlessBrokenPipe(error) {
  if (error.code !== 'EPIPE') throw error;
}

// 父终端关闭时仅忽略标准输出断管道，业务异常仍交给原有处理。
for (const stream of [process.stdout, process.stderr]) {
  stream.on('error', rethrowUnlessBrokenPipe);
}

export const stdioConsole = {};
for (const method of ['log', 'error']) {
  stdioConsole[method] = (...args) => {
    try {
      console[method](...args);
    } catch (error) {
      rethrowUnlessBrokenPipe(error);
    }
  };
}
