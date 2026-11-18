import assert from 'node:assert/strict';
import test from 'node:test';
import {observedWBSearch} from '../src/wb-session.ts';
test('WB reuses the observed API version and region but not arbitrary tokens or old filters',()=>{
  const value=observedWBSearch(['https://u-search.wb.ru/exactmatch/ru/common/v99/search?query=old&dest=123&appType=1&token=private&fbrand=5&page=7'],'худи & oversize');
  const url=new URL(value!);assert.equal(url.pathname,'/exactmatch/ru/common/v99/search');
  assert.equal(url.searchParams.get('dest'),'123');assert.equal(url.searchParams.get('query'),'худи & oversize');
  assert.equal(url.searchParams.get('page'),'1');assert.equal(url.searchParams.get('curr'),'rub');
  assert.equal(url.searchParams.has('token'),false);assert.equal(url.searchParams.has('fbrand'),false);
});
test('WB observed endpoint cannot become an arbitrary network request',()=>{
  for(const value of ['https://evil.test/exactmatch/ru/common/v18/search','https://search.wb.ru/account','http://search.wb.ru/exactmatch/ru/common/v18/search','https://u-search.wb.ru.evil.test/exactmatch/ru/common/v18/search'])assert.equal(observedWBSearch([value],'test'),null);
});
