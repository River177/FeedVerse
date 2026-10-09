// Runs INSIDE an attempt-specific Docker container; no hidden evaluator mounts.
import {readFile, writeFile, appendFile, stat, mkdir} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {pathToFileURL} from 'node:url';
const cfg = JSON.parse(await readFile('/control/input.json', 'utf8'));
const sdk = await import(pathToFileURL(`${cfg.agh_source}/packages/sdk/src/index.node.ts`).href);
await mkdir('/control/home/profiles/local-dev', {recursive:true});
await writeFile('/control/home/profiles/local-dev/profile.yaml',
  `name: local-dev\nschemaVersion: 1\npresets: { default: ${cfg.preset}, allowed: [${cfg.preset}] }\ncomputerUse: { enabled: false }\n`);
const daemon = spawn('node', [`${cfg.agh_source}/packages/cli/dist/local/daemon.mjs`,
  '--home', '/control/home', '--profile', 'local-dev', '--workspace', '/workspace'],
  {stdio: ['ignore', 'inherit', 'inherit'], env: {...process.env, AGH_HOME: '/control/home'}});
let client;
try {
  let owner;
  for (let i=0; i<120; i++) {
    try {
      const candidate=JSON.parse(await readFile('/control/home/data/daemon/owner.json','utf8'));
      if (!(await stat(candidate.socketPath)).isSocket()) throw new Error('socket_not_ready');
      owner=candidate;
      break;
    }
    catch {if (daemon.exitCode!==null) throw new Error('daemon_start_failed'); await new Promise(r=>setTimeout(r,250));}
  }
  if (!owner) throw new Error('daemon_socket_timeout');
  client=sdk.createClient({transport:{kind:'unix',path:owner.socketPath},auth:{kind:'local'},journal:sdk.memoryJournal()});
  await client.initialize();
  const route={providerId:'openai',baseUrl:`http://127.0.0.1:${cfg.port}/v1`,apiKey:cfg.key,model:cfg.model};
  const test=await client.config.test(route);
  if (!test.verified || !test.models.some(m=>m.id===cfg.model)) throw new Error('provider_test_failed');
  const revision=(await client.config.get()).revision;
  await client.config.save({...route,expectedRevision:revision,
    defaultSettings:{thinking:cfg.thinking,contextWindow:cfg.context_window}});
  const session=await client.session.new({cwd:'/workspace',preset:cfg.preset});
  await writeFile('/control/session.json',JSON.stringify({session_id:session.id,preset:cfg.preset}));
  let pending=Promise.resolve();
  session.listeners.add((method,params)=>{
    pending=pending.then(()=>appendFile('/control/trace.jsonl',JSON.stringify({method,params})+'\n'));
  });
  session.onPermissionRequest(async request=>{
    const call=JSON.stringify(request.toolCall);
    // The container is the OS boundary. Never grant persistent approvals.
    let allow=!/subagent|computer_use|web_fetch/i.test(call);
    if(cfg.smoke) allow=call.includes('"command":"python3 solution.py"') || request.toolCall.title==='python3 solution.py';
    await appendFile('/control/permissions.jsonl',JSON.stringify({toolCall:request.toolCall,allowed:allow})+'\n');
    return {verdict:allow?'allowed-once':'rejected'};
  });
  const turn=await session.prompt(cfg.prompt,{signal:AbortSignal.timeout(cfg.task_timeout_seconds*1000)});
  await pending;
  await writeFile('/control/turn.json',JSON.stringify({session_id:session.id,turn},null,2));
  if(turn.reason!=='completed') process.exitCode=2;
} catch(error) {
  await writeFile('/control/error.json',JSON.stringify({type:error.constructor.name,message:String(error.message).slice(0,500)}));
  process.exitCode=1;
} finally {
  if(client) await client.close();
  daemon.kill('SIGTERM');
}
