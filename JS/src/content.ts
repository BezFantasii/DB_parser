import {collectPage} from "./parser.ts";
import {marketplaceFor, type Marketplace} from "./domain.ts";
const scope = globalThis as typeof globalThis & {__marketplaceParserInstalled?: boolean};
if (!scope.__marketplaceParserInstalled) {
  scope.__marketplaceParserInstalled = true;
  let busy = false;
  chrome.runtime.onMessage.addListener((message, _sender, respond) => {
    if (message.target !== "parser" || message.type !== "collect") return;
    if (busy) { respond({accepted: false}); return; }
    busy = true;
    respond({accepted: true});
    void (async () => {
      const meta = {taskId: message.taskId, token: message.token};
      try {
        if (marketplaceFor(location.href) !== message.site) throw new Error("Страница другой площадки");
        const data = await collectPage(message.site as Marketplace, message.kind, message.limit, message.scrolls);
        await chrome.runtime.sendMessage({target: "background", type: "task.result", ...meta, data});
      } catch (e) {
        await chrome.runtime.sendMessage({target: "background", type: "task.result", ...meta, error: String(e instanceof Error ? e.message : e)}).catch(() => {});
      } finally { busy = false; }
    })();
    return false;
  });
}
