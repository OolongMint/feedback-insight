// Real report behavior checks: Node 22+ and Chrome/Edge, no npm dependencies.
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { tmpdir } from 'node:os';
import { mkdtemp } from 'node:fs/promises';

const browser = process.env.BROWSER_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const report = resolve(process.argv[2] || 'reports/demo/report.html');
const output = resolve(process.env.REPORT_BROWSER_OUTPUT || 'reports/browser');
await mkdir(output, { recursive: true });
const profile = await mkdtemp(resolve(tmpdir(), 'feedback-browser-'));
const child = spawn(browser, [
  '--headless=new', '--disable-gpu', '--no-sandbox', '--disable-extensions', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
let socket;
try {
  const endpoint = await new Promise((done, reject) => {
    let errorOutput = '';
    const timer = setTimeout(() => reject(new Error('Browser startup timed out')), 15000);
    child.on('error', reject);
    child.on('exit', code => { if (code) reject(new Error(`Browser exited ${code}`)); });
    child.stderr.on('data', chunk => {
      errorOutput += chunk.toString();
      if (process.env.DEBUG_BROWSER) process.stderr.write(chunk);
      const match = errorOutput.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timer); done(match[1]); }
    });
  });
  socket = new WebSocket(endpoint);
  await new Promise((done, reject) => { socket.onopen = done; socket.onerror = reject; });
  let nextId = 0;
  const pending = new Map();
  const errors = [];
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
    const item = pending.get(message.id);
    if (item) {
      clearTimeout(item.timer);
      pending.delete(message.id);
      if (message.error) item.reject(new Error(message.error.message)); else item.done(message.result);
    }
  };
  const call = (method, params = {}, sessionId) => new Promise((done, reject) => {
    const id = ++nextId;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} timeout`)); }, method === 'Page.printToPDF' ? 45000 : 12000);
    pending.set(id, { done, reject, timer });
    socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  const { targetId } = await call('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await call('Target.attachToTarget', { targetId, flatten: true });
  if (process.env.DEBUG_BROWSER) console.log(await call('Target.getTargets'));
  await call('Runtime.enable', {}, sessionId);
  await call('Page.enable', {}, sessionId);
  const evaluate = async expression => {
    const response = await call('Runtime.evaluate', { expression: `JSON.stringify(${expression})`, returnByValue: true }, sessionId);
    if (response.exceptionDetails) throw new Error(`Browser evaluation failed: ${response.exceptionDetails.text}`);
    return JSON.parse(response.result.value);
  };
  const requireChecks = (checks, description) => {
    if (!Object.values(checks).every(Boolean)) throw new Error(`${description}: ${JSON.stringify(checks)}`);
  };
  const results = [];
  for (const width of [1440, 768, 390]) {
    await call('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false }, sessionId);
    await call('Page.navigate', { url: pathToFileURL(report).href }, sessionId);
    await new Promise(done => setTimeout(done, 400));
    const metrics = await evaluate(`({
      title:document.title, width:innerWidth, documentWidth:document.documentElement.scrollWidth,
      bodyText:document.body.innerText.length, inputs:document.querySelectorAll('input').length,
      background:getComputedStyle(document.body).backgroundColor,
      bodyFont:getComputedStyle(document.body).fontSize,
      heading:document.querySelector('h1')?.textContent,
      headingSize:document.querySelector('h1')&&getComputedStyle(document.querySelector('h1')).fontSize,
      sidebar:document.querySelectorAll('aside').length,
      feedbackRows:document.querySelectorAll('#feedback-rows tr').length,
      externalAssets:[...document.querySelectorAll('script[src],link[href],img[src]')].map(e=>e.src||e.href).filter(s=>/^https?:/.test(s))
    })`);
    if (metrics.documentWidth > width + 1) throw new Error(`Horizontal overflow at ${width}: ${metrics.documentWidth}`);
    if (metrics.bodyText < 200) throw new Error(`Empty report at ${width}`);
    if (metrics.externalAssets.length) throw new Error('Report depends on remote assets');
    if (metrics.background !== 'rgb(21, 24, 29)' || metrics.heading !== '用户反馈分析报告' || metrics.sidebar) {
      throw new Error(`Report design does not match approved direction: ${JSON.stringify(metrics)}`);
    }
    if (metrics.bodyFont !== '15px' || metrics.headingSize !== '26px') throw new Error('Report font scale changed');
    const { data } = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }, sessionId);
    await writeFile(resolve(output, `report-${width}.png`), Buffer.from(data, 'base64'));
    results.push(metrics);
  }
  const initialEvidence = await evaluate(`(()=>{
    const articles=[...document.querySelectorAll('article')].filter(a=>a.querySelector('blockquote'));
    return {
      hasEvidence:articles.length>0,
      twoByDefault:articles.every(a=>[...a.querySelectorAll('blockquote')].filter(q=>!q.closest('details')).length===Math.min(2,a.querySelectorAll('blockquote').length)),
      nativeRemainder:articles.every(a=>a.querySelectorAll('blockquote').length<=2||!!a.querySelector('details:not([open]) summary')),
      uniqueSourceIds:(()=>{const ids=[...document.querySelectorAll('[id^="source-"]')].map(e=>e.id);return ids.length===new Set(ids).size&&ids.length===document.querySelectorAll('#feedback-rows tr').length})()
    };
  })()`);
  requireChecks(initialEvidence, 'Evidence structure failure');
  await evaluate(`(()=>{document.querySelector('article details summary')?.focus();return true})()`);
  await call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', text: '\r', unmodifiedText: '\r', windowsVirtualKeyCode: 13 }, sessionId);
  await call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 }, sessionId);
  const keyboard = await evaluate(`({focusedNativeSummary:document.activeElement?.tagName==='SUMMARY',keyboardExpanded:!!document.querySelector('article details')?.open})`);
  requireChecks(keyboard, 'Keyboard evidence toggle failure');
  const interactions = await evaluate(`(()=>{
      const search=document.getElementById('search');
      search.value='__NO_MATCH_SENTINEL__'; search.dispatchEvent(new Event('input'));
      const rows=[...document.querySelectorAll('#feedback-rows tr')];
      const emptyState=!document.getElementById('no-results').hidden&&rows.every(r=>r.hidden);
      const summaryUnaffected=[...document.querySelectorAll('tbody:not(#feedback-rows) tr')].every(r=>!r.hidden);
      search.value=''; search.dispatchEvent(new Event('input'));
      const topic=document.getElementById('topic-filter');
      topic.selectedIndex=1; topic.dispatchEvent(new Event('change'));
      const shown=rows.filter(r=>!r.hidden);
      const topicFilter=shown.length>0&&shown.every(r=>r.dataset.topic===topic.value);
      const sentiment=document.getElementById('sentiment-filter');
      topic.value='';topic.dispatchEvent(new Event('change'));
      sentiment.value='负向';sentiment.dispatchEvent(new Event('change'));
      const sentimentFilter=rows.some(r=>!r.hidden)&&rows.filter(r=>!r.hidden).every(r=>r.dataset.sentiment==='负向');
      const topicLink=document.querySelector('a[href^="#topic-"]');
      topicLink?.click();
      const topicJump=!!topicLink&&location.hash===topicLink.getAttribute('href')&&!!document.querySelector(location.hash);
      const citation=document.querySelector('blockquote a[href^="#source-"]');
      citation?.click();
      const sourceLink=!!citation&&!document.querySelector(citation.getAttribute('href')).hidden&&topic.value===''&&sentiment.value===''&&search.value===''&&location.hash===citation.getAttribute('href');
      return {emptyState,summaryUnaffected,topicFilter,sentimentFilter,topicJump,sourceLink};
    })()`);
  requireChecks(interactions, 'Interaction failure');

  // Test a deliberately non-default user state, including an open disclosure
  // and an empty filtered table. Snapshotting twice must not lose that state.
  const printState = await evaluate(`(()=>{
    const ds=[...document.querySelectorAll('article details')];
    ds.forEach((d,i)=>d.open=i===0);
    document.getElementById('search').value='__NO_MATCH_SENTINEL__';
    document.getElementById('search').dispatchEvent(new Event('input'));
    document.getElementById('topic-filter').selectedIndex=1;
    document.getElementById('topic-filter').dispatchEvent(new Event('change'));
    document.getElementById('sentiment-filter').value='负向';
    document.getElementById('sentiment-filter').dispatchEvent(new Event('change'));
    window.__reportQaState=()=>({
      details:[...document.querySelectorAll('article details')].map(d=>d.open),
      hidden:[...document.querySelectorAll('#feedback-rows tr')].map(r=>r.hidden),
      search:document.getElementById('search').value,
      topic:document.getElementById('topic-filter').value,
      sentiment:document.getElementById('sentiment-filter').value,
      count:document.getElementById('result-count').textContent,
      empty:document.getElementById('no-results').hidden
    });
    const before=JSON.stringify(window.__reportQaState());
    window.dispatchEvent(new Event('afterprint'));
    const afterWithoutBefore=JSON.stringify(window.__reportQaState())===before;
    window.dispatchEvent(new Event('beforeprint'));
    const allEvidenceOpen=[...document.querySelectorAll('article details')].every(d=>d.open);
    const allRowsVisible=[...document.querySelectorAll('#feedback-rows tr')].every(r=>!r.hidden);
    const noFalseEmpty=document.getElementById('no-results').hidden;
    window.dispatchEvent(new Event('beforeprint'));
    window.dispatchEvent(new Event('afterprint'));
    const exactRestoration=JSON.stringify(window.__reportQaState())===before;
    window.__reportQaSaved=before;
    window.__reportQaPrintEvents=[];
    window.addEventListener('beforeprint',()=>window.__reportQaPrintEvents.push({
      type:'before',allRows:[...document.querySelectorAll('#feedback-rows tr')].every(r=>!r.hidden),
      allEvidence:[...document.querySelectorAll('article details')].every(d=>d.open)
    }));
    window.addEventListener('afterprint',()=>window.__reportQaPrintEvents.push({type:'after',restored:JSON.stringify(window.__reportQaState())===window.__reportQaSaved}));
    return {afterWithoutBefore,allEvidenceOpen,allRowsVisible,noFalseEmpty,exactRestoration};
  })()`);
  requireChecks(printState, 'Print state failure');

  await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false }, sessionId);
  const pdf = await call('Page.printToPDF', {
    printBackground: true, preferCSSPageSize: true, displayHeaderFooter: false,
    paperWidth: 8.27, paperHeight: 11.69,
  }, sessionId);
  await writeFile(resolve(output, 'report-print.pdf'), Buffer.from(pdf.data, 'base64'));
  await new Promise(done => setTimeout(done, 100));
  const actualPrint = await evaluate(`({
    beforeEvent:window.__reportQaPrintEvents.some(e=>e.type==='before'&&e.allRows&&e.allEvidence),
    afterEvent:window.__reportQaPrintEvents.some(e=>e.type==='after'&&e.restored),
    stateRestored:JSON.stringify(window.__reportQaState())===window.__reportQaSaved
  })`);
  requireChecks(actualPrint, 'Actual browser PDF printing failure');
  await call('Emulation.setEmulatedMedia', { media: 'print' }, sessionId);
  await evaluate(`(()=>{window.dispatchEvent(new Event('beforeprint'));scrollTo(0,0);return true})()`);
  const printAppearance = await evaluate(`({
    whiteBackground:getComputedStyle(document.body).backgroundColor==='rgb(255, 255, 255)',
    darkText:(()=>{const c=getComputedStyle(document.body).color.match(/\\d+/g).map(Number);return c.slice(0,3).every(v=>v<100)})(),
    readableTables:[...document.querySelectorAll('.table-wrap')].every(w=>getComputedStyle(w).overflowX==='visible')
  })`);
  requireChecks(printAppearance, 'Print appearance failure');
  const printShot = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }, sessionId);
  await writeFile(resolve(output, 'report-print.png'), Buffer.from(printShot.data, 'base64'));
  await call('Emulation.setEmulatedMedia', { media: 'screen' }, sessionId);
  await evaluate(`(()=>{window.dispatchEvent(new Event('afterprint'));return true})()`);
  if (errors.length) throw new Error(`JavaScript errors: ${errors.join(', ')}`);
  const checks = { passed: true, viewports: results, initialEvidence, keyboard, interactions, printState, actualPrint, printAppearance, javascriptErrors: errors };
  await writeFile(resolve(output, 'checks.json'), JSON.stringify(checks, null, 2));
  console.log(JSON.stringify(checks, null, 2));
  await call('Browser.close');
} finally {
  socket?.close();
  child.kill();
}
