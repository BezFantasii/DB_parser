import assert from 'node:assert/strict';
import test from 'node:test';
import {backendOrigin,backendOffers} from '../src/backend-search.ts';
import type {Comparison} from '../src/comparison.ts';
const job={target:'ozon'} as Comparison;
test('backend URL permits loopback HTTP or HTTPS without credentials or paths',()=>{
  assert.equal(backendOrigin('http://127.0.0.1:8000'),'http://127.0.0.1:8000');
  assert.equal(backendOrigin('https://parser.example/'),'https://parser.example');
  for(const url of ['http://remote.example','https://user:pass@parser.example','https://parser.example/api','https://parser.example?token=secret'])assert.throws(()=>backendOrigin(url));
});
test('backend observations preserve decimal prices and validate marketplace and currency',()=>{
  const p={name:'Худи',url:'https://www.ozon.ru/product/hudi-123/',price:'1234.50',currency:'RUB',price_kind:'card'};
  assert.equal(backendOffers([{data:p}],job)[0].price,'1234.50');
  assert.equal(backendOffers([{data:{...p,price:null}},{data:{...p,currency:'USD'}}],job).length,0);
  assert.throws(()=>backendOffers([{data:{...p,url:'https://evil.test/product/hudi-123/'}}],job));
});
