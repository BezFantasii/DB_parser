import assert from 'node:assert/strict';
import test from 'node:test';
import {popupState} from '../src/popup-state.ts';
test('popup stays usable with the older worker response instead of reading undefined.mode',()=>{
  const state=popupState({enabled:true,job:null});
  assert.equal(state.missingSettings,true);assert.equal(state.backend.mode,'browser');assert.equal(state.job,null);
});
test('popup handles null settings and preserves valid current settings',()=>{
  assert.equal(popupState({backend:null}).backend.mode,'browser');
  assert.equal(popupState({enabled:false,backend:{mode:'backend',url:'http://localhost:8000',token:'sample'}}).backend.token,'sample');
  assert.equal(popupState({enabled:false}).enabled,false);
  assert.throws(()=>popupState(undefined),/Обновите расширение/);
});
