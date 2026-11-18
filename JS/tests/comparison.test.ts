import assert from 'node:assert/strict';
import test from 'node:test';
import {partnerSearch,searchContext,validOffer} from '../src/comparison.ts';
import {wbOffers,wbSearchURL} from '../src/search-http.ts';
import {ozonComposerURL,ozonJSONOffers} from '../src/ozon-session.ts';

test('Ozon composer encodes the search path and parses only actual search tiles',()=>{
  const url=ozonComposerURL('https://www.ozon.ru/search/?text=худи%20%26%20oversize');
  assert.equal(new URL(new URL(url).searchParams.get('url')!,'https://www.ozon.ru').searchParams.get('text'),'худи & oversize');
  const tile={action:{link:'/product/hudi-123/'},mainState:[{priceV2:{price:[{text:'2 399 ₽'}],oldPrice:{text:'5 999 ₽'}}},{textAtom:{text:'Худи мужское'}}]};
  const payload={widgetStates:{'searchResultsV2-1':JSON.stringify({items:[tile,tile,{action:{link:'https://evil.test/product/a-5/'}}]}),'recommendations-2':JSON.stringify({items:[{...tile,action:{link:'/product/other-456/'}}]})}};
  assert.deepEqual(ozonJSONOffers(payload).map(p=>[p.name,p.price,p.url]),[['Худи мужское','2399','https://www.ozon.ru/product/hudi-123/']]);
  assert.deepEqual(ozonJSONOffers({widgetStates:{'searchResultsV2-1':'invalid'}}),[]);
  assert.throws(()=>ozonComposerURL('https://evil.test/search/?text=hudi'));
});
test('live Ozon tileGridDesktop uses textDS and separates card price from original price',()=>{
  const item={action:{link:'/product/hudi-999/?at=tracking'},mainState:[{priceV2:{price:[{text:'5 999 ₽',textStyle:'ORIGINAL_PRICE'},{text:'1\u2009234\u2009₽',textStyle:'PRICE'}],priceStyle:{styleType:'CARD_PRICE'}}},{type:'textDS',id:'name',textDS:{text:'Худи мужское'}}]};
  const result=ozonJSONOffers({widgetStates:{'tileGridDesktop-1':JSON.stringify({items:[item]})}});
  assert.equal(result[0]?.price,'1234');assert.equal(result[0]?.name,'Худи мужское');
  assert.match(result[0]?.priceNote,/Ozon Картой/);
  assert.equal(result[0]?.url,'https://www.ozon.ru/product/hudi-999/');
});

test('Ozon category search keeps the user query',()=>{
  assert.deepEqual(searchContext('https://www.ozon.ru/category/naushniki-15555/?text=Sony'),{site:'ozon',query:'Sony'});
  assert.equal(new URL(wbSearchURL('Sony & JBL')).searchParams.get('query'),'Sony & JBL');
});
test('WB JSON handles modern and legacy kopeck prices and skips unavailable offers',()=>{
  assert.deepEqual(wbOffers({data:{products:[{id:12,name:'Sony',sizes:[{price:{product:123450}},{price:{product:150000}}]},{id:13,name:'JBL',salePriceU:99999},{id:14,name:'Нет цены'},{id:12,name:'Дубль',salePriceU:1}]}}).map(p=>p.price),['1234.50','999.99']);
  assert.equal(wbOffers({products:[{id:'javascript:1',name:'Bad',salePriceU:100}]}).length,0);
});

test('search URLs are recognized and the same query is encoded for the partner',()=>{
  const query='наушники Sony & JBL + ANC';
  const url=partnerSearch(query,'wb');
  assert.deepEqual(searchContext(url),{site:'ozon',query});
  assert.deepEqual(searchContext(partnerSearch(query,'ozon')),{site:'wb',query});
  assert.equal(searchContext('https://www.ozon.ru/search/?text=%20Sony%20%20ANC%20')?.query,'Sony ANC');
});
test('non-search pages and unrelated or unsafe hosts never trigger a comparison',()=>{
  for(const url of ['https://www.ozon.ru/product/test-123/?text=hello','https://evil.example/search/?text=hello','https://ozon.ru.evil.example/search/?text=hello','http://ozon.ru/search/?text=hello','https://www.wildberries.ru/catalog/0/search.aspx?search=','not a url'])assert.equal(searchContext(url),null);
});
test('offers require canonical partner URLs and a positive numeric price',()=>{
  const item={name:'Sony',url:'https://www.wildberries.ru/catalog/123/detail.aspx',price:'1299.50',priceNote:'Цена из выдачи'};
  assert.equal(validOffer(item,'wb'),true);
  assert.equal(validOffer(item,'ozon'),false);
  for(const price of ['0','-1','NaN','1e4','1299 ₽'])assert.equal(validOffer({...item,price},'wb'),false);
  assert.equal(validOffer({...item,url:'javascript:alert(1)'},'wb'),false);
});
