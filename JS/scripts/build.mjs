import {build} from 'esbuild';
import {cp,mkdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const dist=path.join(root,'dist');
await mkdir(path.join(dist,'vendor'),{recursive:true});
await build({absWorkingDir:root,entryPoints:{background:'src/background.ts',offscreen:'src/offscreen.ts','sqlite.worker':'src/sqlite.worker.ts',ui:'src/ui.ts',process:'src/process.ts'},outdir:dist,bundle:true,format:'esm',platform:'browser',target:'chrome116',sourcemap:true,plugins:[{name:'sqlite-vendor',setup(b){b.onResolve({filter:/^@sqlite\.org\/sqlite-wasm$/},()=>({path:'./vendor/index.mjs',external:true}));}}]});
await build({absWorkingDir:root,entryPoints:['src/content.ts'],outfile:path.join(dist,'content.js'),bundle:true,format:'iife',platform:'browser',target:'chrome116',sourcemap:true});
for(const file of ['manifest.json','advanced.html','offscreen.html','app.css','fonts.css','process.css'])await cp(path.join(root,file),path.join(dist,file));
await cp(path.join(root,'process.html'),path.join(dist,'index.html'));
for(const file of ['index.mjs','sqlite3.wasm','sqlite3-opfs-async-proxy.js'])await cp(path.join(root,'node_modules/@sqlite.org/sqlite-wasm/dist',file),path.join(dist,'vendor',file));
await cp(path.join(root,'node_modules/@sqlite.org/sqlite-wasm/README.md'),path.join(dist,'vendor/SQLITE-README.md'));
// Small packaged PNG for desktop notifications; no remote assets.
await writeFile(path.join(dist,'icon.png'),Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64'));
console.log(`Extension built: ${dist}`);
