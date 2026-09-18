// eslint-disable-next-line no-unused-expressions -- Playwright CLI evaluates this function.
async (page) => {
  await page.reload();
  const fixtureResponse = await page.request.get('http://127.0.0.1:8768/response.json');
  if (!fixtureResponse.ok()) throw new Error('Comparison fixture is unavailable');
  const fixture = await fixtureResponse.json();
  await page.evaluate(data => renderPlan(data), fixture);
  const expectedDays = fixture.plan.days.length;
  const expectedStops = fixture.plan.days.flatMap(day => day.schedule);
  const expectedRests = expectedStops.filter(item => item.type === 'free_time').length;
  const expectedVisits = expectedStops.filter(item => item.type === 'visit').length;
  const results = [];
  for (const viewport of [{width:1365,height:900},{width:390,height:844},{width:320,height:740}]) {
    await page.setViewportSize(viewport);
    await page.locator('.guide-cover').scrollIntoViewIfNeeded();
    await page.locator('.guide-cover').evaluate(element => element.scrollIntoView({block:'start',behavior:'instant'}));
    const state = await page.evaluate(() => ({
      stamp:document.querySelector('.guide-stamp').textContent,
      restLabels:Array.from(document.querySelectorAll('.stop-free_time .stop-kind'),el=>el.textContent),
      horizontalOverflow:document.documentElement.scrollWidth > window.innerWidth,
      dayCount:document.querySelectorAll('.day-card').length,
      visitCount:document.querySelectorAll('.trip-statbar b')[1].textContent,
      evidence:document.querySelector('.evidence-strip').textContent.replace(/\s+/g,' ').trim(),
      clocks:document.querySelectorAll('.stop-clock').length,
      dinnerHasInboundBeforeIt:(() => {
        const rows = Array.from(document.querySelectorAll('.timeline .route-hop,.timeline .timeline-row'));
        const dinner = rows.findIndex(row => row.textContent.includes('洪崖洞附近晚餐'));
        return dinner < 0 || rows.slice(0,dinner).some(row => row.classList.contains('route-hop') && row.textContent.includes('洪崖洞民俗风貌区'));
      })(),
    }));
    if (!state.stamp.includes('完整度') || state.stamp.includes('READY')) throw new Error('Misleading readiness label');
    if (state.restLabels.length !== expectedRests || state.restLabels.some(label=>label !== '闲')) throw new Error('Incorrect free-time label');
    if (state.horizontalOverflow || state.dayCount !== expectedDays) throw new Error('Invalid responsive result layout');
    if (state.visitCount !== `${expectedVisits} 个游览点`) throw new Error('Rest was counted as sightseeing');
    if (state.clocks !== expectedStops.length || !state.dinnerHasInboundBeforeIt) throw new Error('Timeline timing or meal transfer is wrong');
    await page.screenshot({path:`output/playwright/tour-pass-comparison-${viewport.width}.png`});
    results.push({viewport,...state});
  }
  await page.setViewportSize({width:1100,height:900});
  await page.locator('.guide-day').screenshot({path:'output/playwright/chongqing-day-detail.png'});
  const css = await (await page.request.get('http://127.0.0.1:8767/static/styles.css')).text();
  const markup = await page.locator('#result').evaluate(element => {
    const copy = element.cloneNode(true);
    copy.querySelectorAll('.plan-actions,.run-trace').forEach(node=>node.remove());
    return copy.innerHTML;
  });
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>重庆一日行程 · 实测修复版</title><style>${css}\n.snapshot{max-width:1100px;margin:24px auto}.snapshot-note{padding:16px;background:#eef3ed;line-height:1.8}@media(max-width:760px){.snapshot{margin:0}} .snapshot .guide-drawer{display:block}</style></head><body><main class="snapshot"><p class="snapshot-note">2026-09-17 实测修复版。复用 212.509 秒真实生成的模型输出，重新查询地图并组装日程；不是一次新的完整生成。住宿为区域参考点，餐厅、开放、预约与无障碍条件仍待确认。四段公共交通接驳步行合计约 2.68 公里，尚不含景点内步行，不能保证满足少走路需求。可用浏览器打印保存 PDF。</p>${markup}</main></body></html>`;
  const downloading = page.waitForEvent('download');
  await page.evaluate(content => {
    const anchor = document.createElement('a');
    const url = URL.createObjectURL(new Blob([content],{type:'text/html;charset=utf-8'}));
    anchor.href = url; anchor.download = 'chongqing-itinerary-20260917.html';
    anchor.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  }, html);
  await (await downloading).saveAs('output/chongqing-itinerary-20260917.html');
  return {mode:'recorded_result_render_only_not_live_sse',results};
}
