// Local HTTPS fixtures reached through an HTTP CONNECT proxy. Unlike CDP
// interception, this also covers the first request of extension-created tabs.
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import {generateKeyPairSync,sign,randomBytes} from 'node:crypto';

function certificate(){
  const der=(tag,...values)=>{const data=Buffer.concat(values);let length=data.length;
    const bytes=[];while(length){bytes.unshift(length&255);length>>>=8;}
    return Buffer.concat([Buffer.from([tag,...(data.length<128?[data.length]:[0x80|bytes.length,...bytes])]),data]);};
  const seq=(...values)=>der(0x30,...values);
  const integer=value=>der(2,Buffer.from([value]));
  const oid=hex=>der(6,Buffer.from(hex,'hex'));
  const algorithm=seq(oid('2a864886f70d01010b'),der(5,Buffer.alloc(0)));
  const name=seq(der(0x31,seq(oid('550403'),der(0x0c,Buffer.from('Local extension test')))));
  const time=date=>der(0x17,Buffer.from(date.toISOString().slice(2,19).replace(/[-:T]/g,'')+'Z'));
  const {privateKey,publicKey}=generateKeyPairSync('rsa',{modulusLength:2048});
  const serial=randomBytes(16);serial[0]&=0x7f;
  const tbs=seq(der(0xa0,integer(2)),der(2,serial),algorithm,name,
    seq(time(new Date(Date.now()-86400000)),time(new Date(Date.now()+86400000))),name,
    publicKey.export({format:'der',type:'spki'}));
  const cert=seq(tbs,algorithm,der(3,Buffer.from([0]),sign('sha256',tbs,privateKey)));
  return {key:privateKey.export({format:'pem',type:'pkcs8'}),cert:`-----BEGIN CERTIFICATE-----\n${cert.toString('base64').match(/.{1,64}/g).join('\n')}\n-----END CERTIFICATE-----`};
}
export async function fixtureNetwork(handler){
  const sockets=new Set();
  const track=socket=>{sockets.add(socket);socket.on('close',()=>sockets.delete(socket));};
  const server=https.createServer(certificate(),handler);
  server.on('connection',track);
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const proxy=http.createServer((_request,response)=>{response.writeHead(404);response.end();});
  proxy.on('connection',track);
  proxy.on('connect',(_request,socket,head)=>{
    const upstream=net.connect(server.address().port,'127.0.0.1',()=>{
      socket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
      if(head.length)upstream.write(head);
      socket.pipe(upstream);upstream.pipe(socket);
    });
    track(upstream);upstream.on('error',()=>socket.destroy());socket.on('error',()=>upstream.destroy());
  });
  await new Promise(resolve=>proxy.listen(0,'127.0.0.1',resolve));
  return {args:[`--proxy-server=http://127.0.0.1:${proxy.address().port}`,'--ignore-certificate-errors'],
    async close(){for(const socket of sockets)socket.destroy();await Promise.all([new Promise(resolve=>server.close(resolve)),new Promise(resolve=>proxy.close(resolve))]);}};
}
