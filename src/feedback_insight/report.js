(() => {
  'use strict';
  const search = document.getElementById('search');
  const topic = document.getElementById('topic-filter');
  const sentiment = document.getElementById('sentiment-filter');
  const count = document.getElementById('result-count');
  const empty = document.getElementById('no-results');
  const rows = Array.from(document.querySelectorAll('#feedback-rows > tr'));
  const disclosures = Array.from(document.querySelectorAll('details.quote-overflow'));
  let printSnapshot = null;

  function filterRows() {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    for (const row of rows) {
      const matches = row.textContent.toLowerCase().includes(query)
        && (!topic.value || row.dataset.topic === topic.value)
        && (!sentiment.value || row.dataset.sentiment === sentiment.value);
      row.hidden = !matches;
      if (matches) visible++;
    }
    count.textContent = '显示 ' + visible + ' / ' + rows.length + ' 条 · 已脱敏';
    empty.hidden = visible > 0;
  }

  function revealSource() {
    search.value = '';
    topic.value = '';
    sentiment.value = '';
    filterRows();
  }

  function preparePrint() {
    if (printSnapshot !== null) return;
    printSnapshot = {
      open: disclosures.map(item => item.open),
      hidden: rows.map(row => row.hidden),
      search: search.value,
      topic: topic.value,
      sentiment: sentiment.value,
      count: count.textContent,
      empty: empty.hidden,
    };
    for (const item of disclosures) item.open = true;
    for (const row of rows) row.hidden = false;
    count.textContent = '显示 ' + rows.length + ' / ' + rows.length + ' 条 · 已脱敏';
    empty.hidden = rows.length > 0;
  }

  function restoreScreen() {
    if (printSnapshot === null) return;
    disclosures.forEach((item, index) => { item.open = printSnapshot.open[index]; });
    rows.forEach((row, index) => { row.hidden = printSnapshot.hidden[index]; });
    search.value = printSnapshot.search;
    topic.value = printSnapshot.topic;
    sentiment.value = printSnapshot.sentiment;
    count.textContent = printSnapshot.count;
    empty.hidden = printSnapshot.empty;
    printSnapshot = null;
  }

  search.addEventListener('input', filterRows);
  topic.addEventListener('change', filterRows);
  sentiment.addEventListener('change', filterRows);
  for (const link of document.querySelectorAll('a[href^="#source-"]')) {
    link.addEventListener('click', revealSource);
  }
  window.addEventListener('beforeprint', preparePrint);
  window.addEventListener('afterprint', restoreScreen);
  document.getElementById('print-report').addEventListener('click', () => window.print());
  if (/^#source-\d+$/.test(window.location.hash)) revealSource();
})();
