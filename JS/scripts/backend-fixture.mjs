// Controlled API for browser client tests. These are explicitly test responses.
import http from 'node:http';
import {randomUUID} from 'node:crypto';
export async function backendFixture(){
  const jobs=new Map(),cancelled=[];
  let behavior='success';
  const server=http.createServer(async(request,response)=>{
    response.setHeader('Content-Type','application/json');
    response.setHeader('Cross-Origin-Resource-Policy','cross-origin');
    const send=(status,value)=>{response.writeHead(status);response.end(JSON.stringify(value));};
    if(request.headers.authorization!=='Bearer test-token')return send(401,{detail:'Invalid token'});
    if(request.url==='/health/ready')return send(200,{status:'ok',database:'ok',workers_online:1});
    if(request.url==='/api/v1/marketplaces')return send(200,{items:[]});
    if(request.url==='/api/v1/jobs' && request.method==='POST'){
      let body='';for await(const chunk of request)body+=chunk;
      const input=JSON.parse(body),id=randomUUID();
      const job={id,status:'queued',marketplace:input.marketplace,mode:behavior==='fixture'?'fixture':'live',source:input.source,engine:input.engine,polls:0,behavior};
      jobs.set(id,job);return send(202,job);
    }
    const match=request.url.match(/^\/api\/v1\/jobs\/([0-9a-f-]+)(?:\/(results|cancel))?$/);
    const job=match&&jobs.get(match[1]);if(!job)return send(404,{detail:'Not found'});
    if(match[2]==='cancel'){job.status='cancelled';cancelled.push(job.id);return send(200,job);}
    if(match[2]==='results'){
      const url=job.marketplace==='ozon'?'https://www.ozon.ru/product/hudi-777/':'https://www.wildberries.ru/catalog/777/detail.aspx';
      return send(200,{job,items:[{data:{name:'Тест backend API',url,price:'1234.50',currency:'RUB'}}]});
    }
    job.polls++;
    if(job.behavior==='blocked'){job.status='blocked';job.error='Ozon HTTP 403: серверная сессия ограничена';}
    else if(job.behavior!=='pending')job.status=job.polls<2?'queued':job.polls<3?'running':'succeeded';
    return send(200,job);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  return {url:`http://127.0.0.1:${server.address().port}`,jobs,cancelled,setBehavior(value){behavior=value;},
    async close(){server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}};
}
