import { formatChangelog } from './changelogMarkdown';

self.onmessage = (event: MessageEvent<string>) => {
  self.postMessage(formatChangelog(event.data));
};
