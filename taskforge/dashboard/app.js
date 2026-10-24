'use strict';
const $ = id => document.getElementById(id);
const state = {token:'',session:null,page:'overview',jobs:[],pipelines:[],runs:[],targets:[],plugins:[],users:[],stats:{},audit:[],query:'',offset:0,refreshing:false};
const pages = {
  overview:['Overview','Workspace pulse','A clear view of your automation and recent execution.','◈'],
  jobs:['Jobs','Scheduled automation','Reusable tasks with explicit schedules and execution policies.','▣'],
  pipelines:['Pipelines','Build and verify','Versioned workflows with dependencies and immutable snapshots.','⌘'],
  runs:['Run history','Execution timeline','Real results, retry attempts, logs, and build artifacts.','◷'],
  deployments:['Deployments','Release control','Promote a verified image digest to an approved environment.','↗'],
  integrations:['Integrations','Connected capabilities','Administrator-configured adapters and capabilities.','◇'],
  users:['Users & access','Access management','Manage team members, roles, and project access tokens.','👥'],
  audit:['Audit trail','Accountability','Configuration changes and execution decisions.','≡']
};
const terminal = new Set(['success','failed','timed_out','cancelled','lost']);
const canOperate = () => ['operator','admin'].includes(state.session?.role);
const isAdmin = () => state.session?.role === 'admin';

function el(tag,props={},...children){
  const node=document.createElement(tag);
  for(const [key,value] of Object.entries(props)){
    if(key.startsWith('on'))node.addEventListener(key.slice(2).toLowerCase(),value);
    else if(key==='className')node.className=value;
    else if(key.startsWith('aria-')&&value!==undefined&&value!==null)node.setAttribute(key,String(value));
    else if(value!==undefined&&value!==null&&value!==false)node.setAttribute(key,value===true?'':value);
  }
  for(const child of children.flat()){
    if(child!==null&&child!==undefined)node.append(child instanceof Node?child:document.createTextNode(String(child)));
  }
  return node;
}

function button(text,action,kind='',disabled=false){
  return el('button',{type:'button',className:kind,onclick:action,disabled},text);
}

function badge(status){
  return el('span',{className:'badge '+(status||'unknown')},(status||'unknown').replaceAll('_',' '));
}

function date(value){
  return value?new Date(typeof value==='number'?value*1000:value).toLocaleString():'—';
}

function formatBytes(bytes){
  if(!bytes||bytes<1024)return(bytes||0)+' B';
  if(bytes<1048576)return(bytes/1024).toFixed(1)+' KB';
  return(bytes/1048576).toFixed(1)+' MB';
}

function toast(message,error=false){
  const item=el('div',{className:'toast'+(error?' error':'')},message);
  $('toast-region').append(item);
  setTimeout(()=>item.remove(),error?9000:5000);
}

async function api(path,options={}){
  const response=await fetch('/api'+path,{
    ...options,
    headers:{
      Authorization:'Bearer '+state.token,
      'Content-Type':'application/json',
      ...(options.headers||{})
    }
  });
  if(!response.ok){
    const body=await response.json().catch(()=>({}));
    if(response.status===401&&state.session)signOut();
    throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail||'Request failed'));
  }
  return response.json();
}

async function action(path,body,success='Request accepted'){
  try{
    const result=await api(path,{method:'POST',...(body!==undefined?{body:JSON.stringify(body)}:{})});
    toast(success);
    await refresh();
    return result;
  }catch(error){
    toast(error.message,true);
    return null;
  }
}

function signOut(){
  sessionStorage.removeItem('taskforge-token');
  state.token='';
  state.session=null;
  $('access-token').value='';
  $('editor').close();
  $('workspace').hidden=true;
  $('login').hidden=false;
  $('access-token').focus();
}

$('login-form').addEventListener('submit',async event=>{
  event.preventDefault();
  $('connect').disabled=true;
  $('login-error').textContent='';
  state.token=$('access-token').value.trim();
  try{
    state.session=await api('/session');
    sessionStorage.setItem('taskforge-token',state.token);
    $('access-token').value='';
    $('login').hidden=true;
    $('workspace').hidden=false;
    $('identity').textContent=state.session.name+' · '+state.session.role;
    buildNavigation();
    navigate(location.hash.slice(1)||'overview');
    await refresh();
  }catch(error){
    $('login-error').textContent=error.message;
    state.token='';
    sessionStorage.removeItem('taskforge-token');
  }finally{
    $('connect').disabled=false;
  }
});

async function initSession(){
  const savedToken=sessionStorage.getItem('taskforge-token');
  if(!savedToken)return;
  state.token=savedToken;
  try{
    state.session=await api('/session');
    $('login').hidden=true;
    $('workspace').hidden=false;
    $('identity').textContent=state.session.name+' · '+state.session.role;
    buildNavigation();
    navigate(location.hash.slice(1)||'overview');
    await refresh();
  }catch(_){
    signOut();
  }
}
initSession();

$('logout').addEventListener('click',signOut);
$('refresh').addEventListener('click',()=>refresh(true));
$('theme').addEventListener('click',()=>{
  const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';
  document.documentElement.dataset.theme=theme;
  localStorage.setItem('taskforge-theme',theme);
  $('theme').textContent=theme==='dark'?'Light mode':'Dark mode';
});

const savedTheme=localStorage.getItem('taskforge-theme')||'dark';
document.documentElement.dataset.theme=savedTheme;
$('theme').textContent=savedTheme==='dark'?'Light mode':'Dark mode';

$('close-dialog').addEventListener('click',()=>$('editor').close());
window.addEventListener('hashchange',()=>{if(state.session)navigate(location.hash.slice(1));});

window.addEventListener('keydown',e=>{
  if(e.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){
    const filter=$('filter');
    if(filter){e.preventDefault();filter.focus();}
  }
});

function buildNavigation(){
  $('navigation').replaceChildren(
    ...Object.entries(pages)
      .filter(([key])=>!['audit','users'].includes(key)||isAdmin())
      .map(([key,page])=>el('a',{href:'#'+key,className:'nav-link','data-page':key},
        el('span',{className:'nav-symbol','aria-hidden':true},page[3]),
        page[0]
      ))
  );
}

function navigate(page){
  state.page=pages[page]&&(!['audit','users'].includes(page)||isAdmin())?page:'overview';
  state.query='';
  state.offset=0;
  render();
  document.querySelectorAll('[data-page]').forEach(link=>
    link.setAttribute('aria-current',link.dataset.page===state.page?'page':'false')
  );
  if(['audit','users'].includes(state.page))refresh();
}

async function refresh(notify=false){
  if(!state.session||state.refreshing)return;
  state.refreshing=true;
  $('refresh').disabled=true;
  try{
    const [jobs,pipelines,runs,stats,targets,plugins]=await Promise.all([
      api('/jobs'),
      api('/pipelines'),
      api('/runs?limit=50&offset='+state.offset),
      api('/system/stats'),
      api('/deployments/targets'),
      api('/plugins')
    ]);
    Object.assign(state,{jobs,pipelines,runs,stats,targets,plugins});
    if(isAdmin()&&state.page==='audit')state.audit=await api('/audit');
    if(isAdmin()&&state.page==='users')state.users=await api('/users');
    $('connection-error').hidden=true;
    $('connection').textContent=stats.workers_online
      ?'Connected · '+stats.workers_online+' worker(s) online'
      :'Connected · no workers online';
    $('updated').textContent='Updated '+new Date().toLocaleTimeString();
    renderContent();
    if(notify)toast('Workspace refreshed');
  }catch(error){
    $('connection-error').textContent='Unable to refresh: '+error.message+'. Showing the last confirmed data.';
    $('connection-error').hidden=false;
    $('connection').textContent='Connection interrupted';
  }finally{
    state.refreshing=false;
    $('refresh').disabled=false;
  }
}

function empty(title,description,label,callback){
  return el('div',{className:'empty'},
    el('div',{className:'empty-symbol','aria-hidden':true},'◇'),
    el('h3',{},title),
    el('p',{},description),
    label?button(label,callback,'primary'):null
  );
}

function panel(title,children,hint=''){
  return el('section',{className:'panel'},
    el('div',{className:'panel-heading'},
      el('h2',{},title),
      el('small',{},hint)
    ),
    children
  );
}

function table(headers,rows){
  return el('div',{className:'table-wrap'},
    el('table',{},
      el('thead',{},
        el('tr',{},headers.map(header=>el('th',{scope:'col'},header)))
      ),
      el('tbody',{},rows)
    )
  );
}

function cell(...children){return el('td',{},...children);}
function nameCell(name,subtitle){
  return cell(el('span',{className:'cell-title'},name),el('small',{},subtitle));
}

function render(){
  const [title,eyebrow,description]=pages[state.page];
  $('page-title').textContent=title;
  $('breadcrumb').textContent=title;
  $('page-eyebrow').textContent=eyebrow;
  $('page-description').textContent=description;
  const actions=[];
  if(['jobs','overview'].includes(state.page)&&isAdmin()){
    actions.push(button('📄 Add from YAML',()=>importYamlDialog('job'),'secondary'));
    actions.push(button('+ Create job',()=>editJob(),'primary'));
  }
  if(state.page==='pipelines'&&isAdmin()){
    actions.push(button('📄 Add from YAML',()=>importYamlDialog('pipeline'),'secondary'));
    actions.push(button('+ Create pipeline',()=>editPipeline(),'primary'));
  }
  if(state.page==='deployments'&&canOperate())actions.push(button('+ Request deployment',()=>deploymentForm(),'primary'));
  if(state.page==='users'&&isAdmin())actions.push(button('+ Add user',()=>createUserForm(),'primary'));
  $('page-actions').replaceChildren(...actions);
  renderContent();
}

function renderContent(){
  const content=$('content'),focused=document.activeElement?.id==='filter',position=focused?document.activeElement.selectionStart:0;
  content.replaceChildren();
  ({overview,jobs:jobsPage,pipelines:pipelinesPage,runs:runsPage,deployments:deploymentsPage,integrations:integrationsPage,users:usersPage,audit:auditPage})[state.page](content);
  if(focused&&$('filter')){$('filter').focus();$('filter').setSelectionRange(position,position);}
}

function overview(content){
  const s=state.stats.statuses||{};
  const stats=[
    ['Configured jobs',state.stats.total_jobs||0,'Reusable automation definitions'],
    ['Active executions',(s.running||0)+(s.queued||0),'Running and queued work'],
    ['Successful runs',s.success||0,'Confirmed successful executions'],
    ['Needs attention',(s.failed||0)+(s.lost||0)+(s.timed_out||0),'Failed, timed out, or interrupted']
  ];
  content.append(el('div',{className:'stat-grid'},
    stats.map(([label,value,caption])=>el('div',{className:'stat-card'},
      el('div',{className:'stat-label'},label,'↗'),
      el('div',{className:'stat-value'},value),
      el('div',{className:'stat-caption'},caption)
    ))
  ));
  content.append(panel('Recent executions',runTable(state.runs.slice(0,8)),'Latest confirmed state'));
  const flow=el('div',{className:'flow'});
  ['Source','Build & test','Artifact','Approval','Deploy'].forEach((name,index)=>{
    if(index)flow.append(el('span',{className:'flow-arrow','aria-hidden':true},'→'));
    flow.append(el('div',{className:'flow-step'},
      el('strong',{},name),
      el('small',{},['Exact commit','Isolated workspace','Verified checksum','Named reviewer','Health verification'][index])
    ));
  });
  content.append(panel('Your release path',el('div',{className:'panel-body'},flow)));
}

function filterToolbar(placeholder){
  return el('div',{className:'toolbar'},
    el('input',{
      id:'filter',
      type:'search',
      placeholder,
      'aria-label':placeholder,
      value:state.query,
      oninput:event=>{state.query=event.target.value;renderContent();}
    })
  );
}

function filtered(items){
  return items.filter(item=>JSON.stringify([item.name,item.id,item.project,item.status]).toLowerCase().includes(state.query.toLowerCase()));
}

function jobsPage(content){
  content.append(filterToolbar('Search jobs by name or project'));
  const jobs=filtered(state.jobs);
  content.append(panel('Job definitions',jobs.length?table(
    ['Job','Schedule','Executor','State','Actions'],
    jobs.map(job=>el('tr',{},
      nameCell(job.name,job.project+' · v'+job.version),
      cell(job.trigger,el('small',{},job.trigger_expr)),
      cell(job.executor),
      cell(badge(job.status)),
      cell(
        button('Run',async()=>{
          const run=await action('/jobs/'+job.id+'/run',undefined,'Run queued');
          if(run)openRun(run.id);
        },'',!canOperate()),
        button(job.status==='paused'?'Resume':'Pause',()=>action('/jobs/'+job.id+'/'+(job.status==='paused'?'resume':'pause')),'',!canOperate()),
        button('YAML',()=>showYamlModal('job',job.id),'quiet'),
        button('Edit',()=>editJob(job),'',!isAdmin()),
        button('Delete',()=>deleteJob(job),'danger',!isAdmin())
      )
    ))
  ):empty(
    state.query?'No matching jobs':'Start with one useful job',
    state.query?'Try another name or project.':'Create a task or import from YAML, choose when it runs, and follow its actual output.',
    isAdmin()&&!state.query?'Add from YAML':'',
    ()=>importYamlDialog('job')
  )));
}

function runTable(runs){
  if(!runs.length)return empty('No executions yet','Run a job or pipeline to see its status, logs, and artifacts here.');
  return table(['Execution','Status','Created','Actions'],runs.map(run=>el('tr',{},
    nameCell(run.name,run.project+' · '+run.kind+(run.commit?' · '+run.commit.slice(0,7):'')),
    cell(badge(run.status)),
    cell(date(run.created)),
    cell(
      button('Inspect',()=>openRun(run.id)),
      run.status==='waiting_approval'&&isAdmin()?button('Review',()=>reviewDeployment(run),'primary'):null,
      run.kind==='deployment'&&['failed','cancelled','lost'].includes(run.status)&&isAdmin()?button('Reconcile',()=>reconcileDeployment(run)):null
    )
  )));
}

function runsPage(content){
  content.append(filterToolbar('Search this page of executions'),panel('Execution history',runTable(filtered(state.runs)),'50 per page'));
  content.append(el('div',{className:'pagination'},
    button('Previous',()=>{state.offset=Math.max(0,state.offset-50);refresh();},'',state.offset===0),
    'Page '+(state.offset/50+1),
    button('Next',()=>{state.offset+=50;refresh();},'',state.runs.length<50)
  ));
}

function pipelinesPage(content){
  content.append(filterToolbar('Search pipelines'));
  const values=filtered(state.pipelines);
  if(!values.length){
    content.append(panel('Pipeline definitions',empty('Connect the steps of your delivery','Create a dependency graph for testing, building, and publishing artifacts.',isAdmin()?'Create pipeline':'',()=>editPipeline())));
    return;
  }
  for(const pipeline of values){
    const flow=el('div',{className:'flow'});
    pipeline.steps.forEach((step,i)=>{
      if(i>0&&step.needs.length)flow.append(el('span',{className:'flow-arrow','aria-hidden':true},'→'));
      const executorIcon={docker:'🐳',python:'🐍',shell:'🐚',http:'🌐'}[step.job.executor]||'⚡';
      flow.append(el('div',{className:'flow-step'},
        el('span',{className:'step-tag'},executorIcon+' '+step.job.executor),
        el('strong',{},step.id),
        el('small',{},step.needs.length?'After: '+step.needs.join(', '):'Starts immediately')
      ));
    });
    content.append(panel(pipeline.name,el('div',{className:'panel-body'},
      el('p',{className:'muted'},pipeline.description||pipeline.project+' · version '+pipeline.version+(pipeline.repository?' · '+pipeline.repository:'')),
      flow,
      el('div',{className:'form-actions'},
        button('YAML',()=>showYamlModal('pipeline',pipeline.id),'quiet'),
        button('Edit definition',()=>editPipeline(pipeline),'',!isAdmin()),
        button('Run pipeline',()=>runPipelineForm(pipeline),'primary',!canOperate())
      )
    ),'v'+pipeline.version));
  }
}

function deploymentsPage(content){
  content.append(el('div',{className:'info-strip'},'Deployments promote the image recorded in a successful build’s release.json artifact. Approval is bound to that digest and target configuration.'));
  if(!state.targets.length){
    content.append(panel('Deployment targets',empty('No targets configured','An administrator can configure Docker or Kubernetes targets. Artifact-only pipelines are already available.')));
  }else{
    content.append(el('div',{className:'grid-2'},state.targets.map(target=>panel(target.environment,el('div',{className:'panel-body'},
      badge(target.type),
      el('p',{className:'muted'},target.project+' · '+target.image_repository),
      el('small',{},target.require_approval?'Requires a different administrator’s approval':'Deploys after validation')
    )))));
  }
  content.append(panel('Recent deployment requests',runTable(state.runs.filter(run=>run.kind==='deployment'))));
}

function integrationsPage(content){
  content.append(el('div',{className:'info-strip'},'Integrations are managed by your administrator. This view reports configured capabilities; it does not simulate connection tests.'));
  content.append(el('div',{className:'grid-2'},state.plugins.map(plugin=>panel(plugin.name,el('div',{className:'panel-body'},
    badge(plugin.enabled?'active':'paused'),
    el('p',{className:'muted'},plugin.enabled?'Configured · '+plugin.type:'Not configured · '+plugin.type)
  )))));
}

function auditPage(content){
  content.append(panel('Recent audit events',state.audit.length?table(
    ['Action','Actor','Target','Time'],
    state.audit.map(item=>el('tr',{},nameCell(item.action,item.project),cell(item.actor),cell(item.target),cell(date(item.created))))
  ):empty('No audit events yet','Configuration and execution actions will appear here.')));
}

function usersPage(content){
  const rolesInfo=el('div',{className:'roles-grid'},
    el('div',{className:'role-card'},
      el('div',{style:'display:flex;align-items:center;gap:8px;margin-bottom:6px;'},
        el('span',{className:'badge admin'},'admin'),
        el('strong',{},'Administrator')
      ),
      el('p',{className:'hint',style:'margin:0;'},'Full control over definitions, pipelines, deployments, plugins, audit trail, and user access.')
    ),
    el('div',{className:'role-card'},
      el('div',{style:'display:flex;align-items:center;gap:8px;margin-bottom:6px;'},
        el('span',{className:'badge operator'},'operator'),
        el('strong',{},'Operator')
      ),
      el('p',{className:'hint',style:'margin:0;'},'Operational execution, manual runs, pausing/resuming jobs, cancellation, and deployment promotion.')
    ),
    el('div',{className:'role-card'},
      el('div',{style:'display:flex;align-items:center;gap:8px;margin-bottom:6px;'},
        el('span',{className:'badge viewer'},'viewer'),
        el('strong',{},'Viewer')
      ),
      el('p',{className:'hint',style:'margin:0;'},'Read-only visibility for definitions, real execution timelines, live streaming logs, and artifacts.')
    )
  );

  const filtered=(state.users||[]).filter(user=>{
    const q=state.query.toLowerCase().trim();
    if(!q)return true;
    return user.name.toLowerCase().includes(q)||
           user.role.toLowerCase().includes(q)||
           (user.projects||[]).some(p=>p.toLowerCase().includes(q))||
           (user.source||'').toLowerCase().includes(q);
  });

  const rows=filtered.map(user=>el('tr',{},
    nameCell(user.name,user.created_by?'Created by '+user.created_by+(user.created?' · '+date(user.created):''):'System configuration'),
    cell(el('span',{className:'badge '+user.role},user.role)),
    cell(el('span',{className:'project-tag'},(user.projects||[]).join(', '))),
    cell(el('span',{className:'badge '+(user.source==='db'?'db':'config')},user.source==='db'?'Database':'Config file')),
    cell(el('code',{className:'token-preview-mono'},user.token_preview||'••••••••')),
    cell(
      user.source==='db'
        ? el('div',{style:'display:flex;gap:6px;justify-content:flex-end;'},
            button('Regenerate token',()=>regenerateUserToken(user),'quiet'),
            button('Revoke',()=>deleteUserDialog(user),'danger')
          )
        : el('small',{className:'muted'},'Static (read-only)')
    )
  ));

  content.append(
    rolesInfo,
    panel('Team members & access tokens',
      el('div',{},
        filterToolbar('Filter users by name, role, or project…'),
        filtered.length
          ? table(['User / Identity','Role','Projects','Source','Token hint','Actions'],rows)
          : empty('No matching users found','Try adjusting your search filter or add a new user.')
      ),
      (state.users||[]).length+' registered user(s)'
    )
  );
}

function dialog(title,eyebrow='CONFIGURATION'){
  if($('editor').open)$('editor').close();
  $('dialog-title').textContent=title;
  $('dialog-eyebrow').textContent=eyebrow;
  $('dialog-content').replaceChildren();
  $('editor').showModal();
  return $('dialog-content');
}

function field(label,name,value='',options={}){
  const input=options.choices
    ?el('select',{name,id:'field-'+name},options.choices.map(choice=>el('option',{value:Array.isArray(choice)?choice[0]:choice},Array.isArray(choice)?choice[1]:choice)))
    :el(options.multiline?'textarea':'input',{name,id:'field-'+name,type:options.type||'text',required:options.required,readonly:options.readonly,min:options.min,rows:options.rows,placeholder:options.placeholder||''});
  input.value=value??'';
  return el('div',{className:'field'+(options.full?' full':'')},el('label',{for:'field-'+name},label),input,options.hint?el('p',{className:'hint'},options.hint):null);
}

function saveForm(form,callback,label='Save changes'){
  const error=el('p',{className:'error-text',role:'alert'}),submit=el('button',{type:'submit',className:'primary'},label);
  form.append(error,el('div',{className:'form-actions'},button('Cancel',()=>$('editor').close(),'quiet'),submit));
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    error.textContent='';
    submit.disabled=true;
    try{
      const res=await callback(new FormData(form));
      if(res!==false)$('editor').close();
      await refresh();
    }catch(failure){
      error.textContent=failure.message;
    }finally{
      submit.disabled=false;
    }
  });
  return form;
}

function editJob(job){
  const content=dialog(job?'Edit job':'Create job'),project=state.session.projects[0]==='*'?'default':state.session.projects[0];
  const form=el('form',{},el('div',{className:'form-grid'},
    field('Name','name',job?.name,{required:true}),
    field('ID','id',job?.id||'job-'+Date.now(),{readonly:!!job,required:true}),
    field('Project','project',job?.project||project,{required:true,readonly:!!job}),
    field('Executor','executor',job?.executor||'docker',{choices:['docker','shell','python','http']}),
    field('Trigger','trigger',job?.trigger||'manual',{choices:['manual','interval','cron','oneshot','webhook']}),
    field('Schedule expression','trigger_expr',job?.trigger_expr||'every 5m',{hint:'Cron: 0 2 * * * · Interval: every 5m · One-shot: ISO date with UTC offset'}),
    field('Timezone','timezone',job?.timezone||'UTC'),
    field('Docker image','image',job?.image||'',{hint:'Required for Docker. Prefer an immutable digest.'}),
    field('Command / Python code / HTTP request','command',job?.command||'echo "Hello from TaskForge"',{multiline:true,full:true,required:true}),
    field('Timeout (seconds)','timeout_seconds',job?.timeout_seconds||300,{type:'number',min:1,required:true}),
    field('Additional retry attempts','max_retries',job?.max_retries??0,{type:'number',min:0,required:true}),
    field('Retry delay (seconds)','retry_delay_seconds',job?.retry_delay_seconds||5,{type:'number',min:1,required:true}),
    field('Webhook secret','webhook_secret','',{type:'password',hint:job?.has_webhook_secret?'Configured. Leave blank to keep.':'At least 32 characters; required for webhook jobs.'}),
    field('Artifact files (one path per line)','artifact_paths',(job?.artifact_paths||[]).join('\n'),{multiline:true}),
    field('Secret names (comma separated)','secret_refs',(job?.secret_refs||[]).join(', '),{hint:'Project secret references configured on the runner.'}),
    field('Description','description',job?.description||'',{full:true,multiline:true})
  ));
  content.append(el('div',{className:'info-strip'},'Shell and Python require a trusted host runner. Docker runs with restricted privileges and no network by default.'));
  content.append(saveForm(form,async data=>{
    const value=Object.fromEntries(data.entries());
    for(const key of ['timeout_seconds','max_retries','retry_delay_seconds'])value[key]=Number(value[key]);
    value.artifact_paths=value.artifact_paths.split('\n').map(v=>v.trim()).filter(Boolean);
    value.secret_refs=value.secret_refs.split(',').map(v=>v.trim()).filter(Boolean);
    value.image=value.image||null;
    if(!value.webhook_secret)delete value.webhook_secret;
    value.version=job?.version||0;
    value.status=job?.status||'active';
    value.args=job?.args||[];
    value.tags=job?.tags||[];
    await api('/jobs',{method:'POST',body:JSON.stringify(value)});
    toast(job?'Job updated':'Job created');
  },job?'Save job':'Create job'));
}

function deleteJob(job){
  const content=dialog('Delete '+job.name+'?','CONFIRM DELETION');
  content.append(el('p',{},'This removes the definition and schedule. Existing history is retained. A running execution must be cancelled separately.'));
  content.append(saveForm(el('form'),async()=>{
    await api('/jobs/'+job.id+'?version='+job.version,{method:'DELETE'});
    toast('Job deleted');
  },'Delete job'));
}

async function editPipeline(pipeline){
  const project=state.session.projects[0]==='*'?'default':state.session.projects[0];
  let defaultYaml = '';
  if(pipeline){
    try{
      const res = await fetch('/api/pipelines/'+encodeURIComponent(pipeline.id)+'/yaml',{
        headers:{Authorization:'Bearer '+state.token}
      });
      if(res.ok) defaultYaml = await res.text();
    }catch(_){}
  }
  if(!defaultYaml){
    defaultYaml = `id: ${pipeline?.id || 'pipeline-' + Date.now()}
project: ${pipeline?.project || project}
name: ${pipeline?.name || 'Build and verify'}
description: ${pipeline?.description || 'Test, then collect a release artifact.'}
version: ${pipeline?.version || 0}
steps:
  - id: test
    needs: []
    job:
      id: test
      project: ${pipeline?.project || project}
      name: Run tests
      trigger: manual
      executor: docker
      image: python:3.12-alpine
      command: python -c "print(42)"
  - id: package
    needs: [test]
    job:
      id: package
      project: ${pipeline?.project || project}
      name: Package artifact
      trigger: manual
      executor: docker
      image: alpine:3.20
      command: echo verified > result.txt
      artifact_paths:
        - result.txt
`;
  }
  const content=dialog(pipeline?'Edit pipeline':'Create pipeline','PIPELINE DEFINITION (YAML)');
  content.append(el('p',{className:'muted'},'Define steps and their needs in YAML or JSON. Cycles and unknown dependencies are rejected before saving. Repository pipelines require an allowlisted repository and exact commit.'));
  content.append(saveForm(
    el('form',{},field('Pipeline definition (YAML)','definition',defaultYaml,{multiline:true,rows:20,required:true})),
    async data=>{
      const raw = data.get('definition');
      await api('/pipelines/yaml',{
        method:'POST',
        headers:{'Content-Type':'application/yaml'},
        body:raw
      });
      toast('Pipeline saved');
    },
    'Save pipeline'
  ));
}

function runPipelineForm(pipeline){
  const content=dialog('Run '+pipeline.name,'NEW EXECUTION'),form=el('form');
  if(pipeline.repository){
    form.append(field('Exact commit SHA','commit','',{required:true,hint:'40 lowercase hexadecimal characters. Checkout is verified by the runner.'}));
  }else{
    form.append(el('p',{},'This run uses version '+pipeline.version+'. Later edits will not change this execution.'));
  }
  form.append(field('Runtime parameters (optional)','parameters','',{multiline:true,rows:3,hint:'Key-value pairs (one per line, e.g. ENVIRONMENT=staging, DEBUG=true). Exposed as environment variables.'}));
  content.append(saveForm(form,async data=>{
    const commit=data.get('commit')||null;
    const rawParams=data.get('parameters')||'';
    const parameters={};
    rawParams.split('\n').map(l=>l.trim()).filter(Boolean).forEach(line=>{
      const idx=line.indexOf('=');
      if(idx>0){parameters[line.slice(0,idx).trim()]=line.slice(idx+1).trim();}
    });
    const run=await api('/pipelines/'+pipeline.id+'/run',{method:'POST',body:JSON.stringify({commit,parameters})});
    toast('Pipeline queued: '+run.id);
  },'Queue pipeline'));
}

function deploymentForm(){
  const content=dialog('Request deployment','RELEASE CONTROL');
  if(!state.targets.length){
    content.append(empty('No deployment targets configured','Ask your administrator to configure Docker or Kubernetes targets.'));
    return;
  }
  const sources=state.runs.filter(run=>run.status==='success'&&run.result.artifacts?.some(a=>a.name==='release.json'));
  const form=el('form',{},
    field('Target environment','target',state.targets[0]?.id,{choices:state.targets.map(target=>[target.id,target.environment+' · '+target.type])}),
    field('Successful source run','source_run',sources[0]?.id||'',{choices:sources.map(run=>[run.id,run.name+' · '+date(run.created)])}),
    field('Immutable image digest','image','',{required:true,hint:'repository/image@sha256:… Must match the source run’s release.json artifact.'})
  );
  if(!sources.length)content.append(el('p',{className:'error-text'},'No recent successful build has a release.json artifact. Publish one from a pipeline first.'));
  if(isAdmin())form.append(field('Release intent','rollback','false',{choices:[['false','Deploy forward'],['true','Roll back to an older build']],hint:'Rollback still requires a successful source build and configured approval.'}));
  content.append(saveForm(form,async data=>{
    const value=Object.fromEntries(data);
    value.rollback=value.rollback==='true';
    await api('/deployments',{method:'POST',body:JSON.stringify(value)});
    toast('Deployment request recorded');
  },'Request deployment'));
}

function reconcileDeployment(run){
  const content=dialog('Reconcile interrupted deployment','ENVIRONMENT RECOVERY');
  content.append(el('p',{},'Verify that the previous runner has stopped and inspect the current service and rollback state. Releasing this lock allows another deployment to this environment.'));
  const form=el('form',{},field('Confirmation','confirmation','',{required:true,hint:'Type VERIFIED after completing those checks.'}));
  content.append(saveForm(form,async data=>{
    if(data.get('confirmation')!=='VERIFIED')throw new Error('Type VERIFIED after checking the runner and target.');
    await api('/deployments/'+run.id+'/reconcile',{method:'POST',body:JSON.stringify({confirmed_stopped:true})});
    toast('Environment lock released');
  },'Release environment lock'));
}

function reviewDeployment(run){
  const content=dialog('Review deployment','APPROVAL REQUIRED');
  content.append(
    el('p',{},'Approval authorizes this exact image and target. A different administrator from the requester must approve.'),
    el('div',{className:'info-strip'},'Target: '+run.target,el('br'),'Image: '+run.image)
  );
  content.append(saveForm(el('form'),async()=>{
    await api('/deployments/'+run.id+'/approve',{method:'POST'});
    toast('Deployment approved and queued');
  },'Approve deployment'));
}

function createUserForm(){
  const content=dialog('Add user','USER MANAGEMENT');
  const form=el('form',{},
    el('div',{className:'form-grid'},
      field('Username','name','',{required:true,placeholder:'e.g. devops-bot or alex'}),
      field('Role','role','operator',{choices:[
        ['admin','Admin · Full management & authoring'],
        ['operator','Operator · Trigger pipelines & deployments'],
        ['viewer','Viewer · Read-only logs & runs']
      ]}),
      field('Project access','projects','*',{required:true,hint:'Use * for all projects, or enter comma-separated project names.'}),
      field('Custom token (optional)','token','',{type:'password',hint:'Leave blank to auto-generate a secure 48-byte token. If provided, min 32 chars.'})
    )
  );
  content.append(
    el('div',{className:'info-strip'},'Generated access tokens are shown once upon creation. Store the token in a secure credentials manager.'),
    saveForm(form,async data=>{
      const name=data.get('name').trim();
      const role=data.get('role');
      const rawProj=data.get('projects').trim();
      const rawToken=data.get('token').trim();
      const projects=rawProj.split(',').map(p=>p.trim()).filter(Boolean);
      const result=await api('/users',{
        method:'POST',
        body:JSON.stringify({
          name,
          role,
          projects:projects.length?projects:['*'],
          token:rawToken||null
        })
      });
      showTokenModal(result.name,result.role,result.token);
      return false;
    },'Create user & generate token')
  );
}

function showTokenModal(username,role,token){
  const content=dialog('Access token generated','CREDENTIALS CREATED');
  const copyBtn=el('button',{type:'button',className:'primary'},'📋 Copy token');
  copyBtn.onclick=async()=>{
    try{
      await navigator.clipboard.writeText(token);
      copyBtn.textContent='✓ Copied to clipboard!';
      setTimeout(()=>{copyBtn.textContent='📋 Copy token';},3000);
      toast('Token copied to clipboard');
    }catch(_){
      toast('Could not copy automatically; please copy manually.',true);
    }
  };
  content.append(
    el('div',{className:'token-reveal-card'},
      el('strong',{},'User: '+username+' · Role: '+role),
      el('p',{className:'hint',style:'margin-top:6px;'},'Make sure to copy your access token now. You will not be able to see it again!'),
      el('div',{className:'token-reveal-code',tabIndex:0,'aria-label':'Access token'},token),
      el('div',{style:'display:flex;gap:8px;margin-top:14px;'},
        copyBtn,
        button('Done',()=>$('editor').close(),'quiet')
      )
    )
  );
}

function regenerateUserToken(user){
  const content=dialog('Regenerate access token','ROTATE CREDENTIALS');
  content.append(
    el('p',{},'Are you sure you want to regenerate the access token for ',el('strong',{},user.name),'? The user’s current token will stop working immediately.'),
    saveForm(el('form'),async()=>{
      const result=await api('/users/'+encodeURIComponent(user.name)+'/token',{method:'POST'});
      showTokenModal(result.name,result.role,result.token);
      return false;
    },'Regenerate token')
  );
}

function deleteUserDialog(user){
  const content=dialog('Revoke user access','CONFIRM REVOCATION');
  content.append(
    el('p',{},'Are you sure you want to revoke and delete ',el('strong',{},user.name),'? All existing sessions and operations for this token will be permanently revoked.'),
    saveForm(el('form'),async()=>{
      await api('/users/'+encodeURIComponent(user.name),{method:'DELETE'});
      toast('User '+user.name+' revoked');
    },'Revoke access')
  );
}

const YAML_TEMPLATES = {
  python_cron: {
    label: '🐍 Python cron job',
    yaml: `id: scheduled-python-job
project: default
name: Scheduled Python Task
trigger: cron
trigger_expr: "0 3 * * *"
timezone: UTC
executor: python
command: |
  import sys
  print("Running scheduled maintenance in Python...")
  print("Status: all checks nominal.")
timeout_seconds: 300
max_retries: 2
retry_delay_seconds: 10
description: Scheduled nightly Python maintenance task
`
  },
  docker_task: {
    label: '🐳 Docker task',
    yaml: `id: docker-verify-task
project: default
name: Docker Container Task
trigger: manual
executor: docker
image: python:3.12-alpine
command: |
  python -c "print('Containerized task executing in isolated Docker runner')"
timeout_seconds: 180
max_retries: 1
retry_delay_seconds: 5
description: Containerized verification task
`
  },
  shell_task: {
    label: '🐚 Shell script job',
    yaml: `id: shell-backup-task
project: default
name: Shell Log Archiver
trigger: interval
trigger_expr: "every 6h"
executor: shell
command: |
  echo "Compressing logs and archiving system state..."
  echo "Archive generated successfully."
timeout_seconds: 120
max_retries: 0
retry_delay_seconds: 5
description: Periodic shell archiver
`
  },
  pipeline: {
    label: '⌘ CI/CD Pipeline',
    yaml: `id: build-test-pipeline
project: default
name: Build and Verify Pipeline
description: Multi-step pipeline with parallel test stage and sealed artifact packaging
steps:
  - id: unit-tests
    needs: []
    job:
      id: unit-tests
      project: default
      name: Run Unit Tests
      executor: docker
      image: python:3.12-alpine
      command: |
        python -c "print('Unit tests passed: 42 passed, 0 failed')"
  - id: security-audit
    needs: []
    job:
      id: security-audit
      project: default
      name: Security Scan
      executor: docker
      image: alpine:3.20
      command: |
        echo "Running security audit... 0 vulnerabilities detected."
  - id: package-release
    needs: [unit-tests, security-audit]
    job:
      id: package-release
      project: default
      name: Package Release Artifact
      executor: docker
      image: alpine:3.20
      command: |
        echo '{"release": "v1.0.0", "status": "verified"}' > release.json
      artifact_paths:
        - release.json
`
  }
};

function importYamlDialog(defaultKind='job'){
  const content = dialog('Add task from YAML', 'DECLARATIVE TASK CONFIGURATION');
  const defaultTemplateKey = defaultKind === 'pipeline' ? 'pipeline' : 'python_cron';
  const initialYaml = YAML_TEMPLATES[defaultTemplateKey].yaml;

  const chipsContainer = el('div', {className: 'template-chips'});
  const textarea = el('textarea', {
    id: 'yaml-task-input',
    className: 'yaml-editor',
    rows: 18,
    required: true,
    placeholder: 'Paste or type your Job or Pipeline YAML here…'
  });
  textarea.value = initialYaml;

  const validationBox = el('div', {id: 'yaml-validation-feedback'});

  Object.entries(YAML_TEMPLATES).forEach(([key, tpl]) => {
    const chip = el('button', {
      type: 'button',
      className: 'template-chip' + (key === defaultTemplateKey ? ' active' : '')
    }, tpl.label);
    chip.onclick = () => {
      textarea.value = tpl.yaml;
      chipsContainer.querySelectorAll('.template-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      validationBox.replaceChildren();
    };
    chipsContainer.append(chip);
  });

  const validateBtn = el('button', {type: 'button', className: 'secondary', id: 'btn-validate-yaml'}, '🔍 Validate YAML');
  validateBtn.onclick = async () => {
    validationBox.replaceChildren();
    const raw = textarea.value.trim();
    if (!raw) {
      validationBox.append(el('p', {className: 'error-text'}, 'Please enter YAML content to validate.'));
      return;
    }
    validateBtn.disabled = true;
    try {
      const res = await api('/tasks/validate', {
        method: 'POST',
        headers: {'Content-Type': 'application/yaml'},
        body: raw
      });
      const badgeText = res.kind === 'pipeline'
        ? `✓ Valid pipeline: "${res.name}" (${res.id}) · ${res.steps_count} step(s)`
        : `✓ Valid job: "${res.name}" (${res.id}) · ${res.executor} executor · ${res.trigger}`;
      validationBox.append(el('div', {className: 'yaml-validation-success'}, badgeText));
    } catch (err) {
      validationBox.append(el('p', {className: 'error-text'}, 'Syntax/Validation error: ' + err.message));
    } finally {
      validateBtn.disabled = false;
    }
  };

  const form = el('form', {id: 'yaml-import-form'},
    el('div', {className: 'info-strip'},
      'Define jobs or multi-step DAG pipelines declaratively using clean YAML. Multiple documents (---) are supported.'
    ),
    el('div', {style: 'margin-bottom: 8px;'},
      el('strong', {style: 'font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;'}, 'Quick Templates:'),
      chipsContainer
    ),
    el('div', {className: 'yaml-editor-wrap'},
      textarea
    ),
    validationBox
  );

  const error = el('p', {className: 'error-text', role: 'alert'});
  const submitBtn = el('button', {type: 'submit', className: 'primary', id: 'btn-apply-yaml'}, 'Apply task definition');
  const actions = el('div', {className: 'form-actions'},
    button('Cancel', () => $('editor').close(), 'quiet'),
    validateBtn,
    submitBtn
  );
  form.append(error, actions);

  form.addEventListener('submit', async event => {
    event.preventDefault();
    error.textContent = '';
    submitBtn.disabled = true;
    const raw = textarea.value.trim();
    if (!raw) {
      error.textContent = 'Please provide YAML content.';
      submitBtn.disabled = false;
      return;
    }
    try {
      const result = await api('/tasks/apply', {
        method: 'POST',
        headers: {'Content-Type': 'application/yaml'},
        body: raw
      });
      const count = result.total || (result.applied ? result.applied.length : 1);
      const firstId = result.applied && result.applied[0] ? result.applied[0].id : 'definition';
      toast(`Applied ${count} task(s) successfully (${firstId})`);
      $('editor').close();
      await refresh();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submitBtn.disabled = false;
    }
  });

  content.append(form);
}

async function showYamlModal(kind, id){
  const title = `Export ${kind === 'job' ? 'Job' : 'Pipeline'} YAML`;
  const content = dialog(title, 'DECLARATIVE DEFINITION');

  const loading = el('p', {className: 'muted'}, 'Loading YAML definition…');
  content.append(loading);

  try {
    const res = await fetch(`/api/${kind === 'job' ? 'jobs' : 'pipelines'}/${encodeURIComponent(id)}/yaml`, {
      headers: { Authorization: 'Bearer ' + state.token }
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to export YAML');
    }
    const yamlContent = await res.text();
    loading.remove();

    const textarea = el('textarea', {
      className: 'yaml-editor',
      rows: 18,
      readonly: true,
      tabIndex: 0,
      'aria-label': `${kind} YAML definition`
    });
    textarea.value = yamlContent;

    const copyBtn = el('button', {type: 'button', className: 'primary'}, '📋 Copy YAML');
    copyBtn.onclick = async () => {
      try {
        await navigator.clipboard.writeText(yamlContent);
        copyBtn.textContent = '✓ Copied!';
        setTimeout(() => { copyBtn.textContent = '📋 Copy YAML'; }, 3000);
        toast('YAML copied to clipboard');
      } catch (_) {
        toast('Could not copy automatically; please copy from the text area.', true);
      }
    };

    const downloadBtn = el('button', {type: 'button', className: 'secondary'}, '⬇ Download .yaml');
    downloadBtn.onclick = () => {
      const blob = new Blob([yamlContent], {type: 'application/yaml;charset=utf-8'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${id}.yaml`;
      document.body.append(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast(`Downloaded ${id}.yaml`);
    };

    content.append(
      el('div', {className: 'info-strip'}, `Declarative ${kind} definition for ${id}. You can use this file with "taskforge apply" or import it in any TaskForge workspace.`),
      el('div', {className: 'yaml-editor-wrap'}, textarea),
      el('div', {className: 'form-actions', style: 'margin-top: 14px;'},
        button('Close', () => $('editor').close(), 'quiet'),
        downloadBtn,
        copyBtn
      )
    );
  } catch (err) {
    loading.textContent = 'Error: ' + err.message;
  }
}

async function openRun(id){
  const content=dialog('Execution details','LIVE RUN RECORD');
  const summary=el('div',{},'Loading execution…');
  const termIndicator=el('span',{className:'terminal-indicator live'},'Live streaming');
  const lineCount=el('span',{},'0 lines');
  let autoScroll=true;
  const autoScrollBtn=button('Auto-scroll: ON',()=>{
    autoScroll=!autoScroll;
    autoScrollBtn.textContent=autoScroll?'Auto-scroll: ON':'Auto-scroll: OFF';
  },'quiet');
  const copyBtn=button('Copy log',async()=>{
    if(!output)return;
    try{
      await navigator.clipboard.writeText(output);
      copyBtn.textContent='Copied!';
      setTimeout(()=>{copyBtn.textContent='Copy log';},2000);
    }catch(_){
      toast('Could not copy to clipboard',true);
    }
  },'quiet');

  const termBar=el('div',{className:'terminal-bar'},
    el('div',{},termIndicator),
    el('div',{className:'terminal-actions'},lineCount,autoScrollBtn,copyBtn)
  );
  const logs=el('pre',{className:'log-terminal',tabindex:'0','aria-label':'Execution log'},'Waiting for output…');
  const actions=el('div',{className:'form-actions'});
  const artifacts=el('div');
  const previewBox=el('div',{className:'artifact-preview-wrap',hidden:true});
  const previewHeader=el('div',{className:'artifact-preview-header'});
  const previewContent=el('pre',{className:'artifact-preview-content'});
  previewBox.append(previewHeader,previewContent);

  content.append(summary,el('h3',{},'Execution log'),termBar,logs,el('h3',{},'Build artifacts'),artifacts,previewBox,actions);

  let cursor=0,output='',stopped=false,busy=false;
  const close=()=>{stopped=true;clearInterval(timer);};
  $('editor').addEventListener('close',close,{once:true});

  async function previewArtifact(digest,name){
    try{
      const res=await api('/runs/'+id+'/artifacts/'+digest+'/preview');
      previewHeader.replaceChildren(
        el('strong',{},'Preview: '+name+' ('+formatBytes(res.size)+')'),
        button('Close',()=>previewBox.hidden=true,'quiet')
      );
      previewContent.textContent=res.content;
      previewBox.hidden=false;
    }catch(err){
      toast(err.message,true);
    }
  }

  async function update(){
    if(stopped||busy)return;
    busy=true;
    try{
      const [run,log]=await Promise.all([api('/runs/'+id),api('/runs/'+id+'/logs?after='+cursor)]);
      if(!content.contains(summary)){close();return;}
      cursor=log.cursor;
      output+=log.records.map(record=>record.text).join('');
      const lineTotal=output?output.split('\n').length:0;
      lineCount.textContent=lineTotal+' lines';

      if(terminal.has(run.status)){
        termIndicator.className='terminal-indicator done';
        termIndicator.textContent='Completed ('+run.status+')';
      }else{
        termIndicator.className='terminal-indicator live';
        termIndicator.textContent='Live streaming';
      }

      logs.textContent=output||(terminal.has(run.status)?'No output was recorded.':'Waiting for runner output…');
      if(autoScroll)logs.scrollTop=logs.scrollHeight;

      summary.replaceChildren(
        badge(run.status),
        el('div',{className:'detail-grid'},...[
          ['Execution',run.name],
          ['Project',run.project],
          ['Created',date(run.created)],
          ['Finished',date(run.finished)],
          ['Run ID',run.id],
          ['Revision',run.commit?run.commit.slice(0,8):'Definition v'+(run.definition_version||'—')]
        ].map(([key,value])=>el('div',{className:'detail-item'},el('small',{},key),el('strong',{},value))))
      );

      if(run.result.error)summary.append(el('p',{className:'error-text'},run.result.error));
      if(run.result.steps){
        const stepFlow=el('div',{className:'flow'});
        Object.entries(run.result.steps).forEach(([name,step],idx)=>{
          if(idx>0)stepFlow.append(el('span',{className:'flow-arrow','aria-hidden':true},'→'));
          stepFlow.append(el('div',{className:'flow-step'},
            el('strong',{},name),
            badge(step.status)
          ));
        });
        summary.append(stepFlow);
      }
      if(run.result.attempts?.length){
        summary.append(el('p',{className:'hint'},run.result.attempts.map(a=>'Attempt '+a.number+': exit '+a.exit_code+', '+a.duration_seconds+'s').join(' · ')));
      }

      const runArtifacts=run.result.artifacts||[];
      if(!runArtifacts.length){
        artifacts.replaceChildren(el('p',{className:'hint'},'No artifacts were published in this run.'));
      }else{
        artifacts.replaceChildren(...runArtifacts.map(artifact=>el('div',{className:'artifact'},
          el('div',{},
            el('strong',{},artifact.name),
            el('small',{},'SHA256: '+artifact.sha256.slice(0,16)+'… · '+formatBytes(artifact.size))
          ),
          el('div',{className:'artifact-actions'},
            button('Preview',()=>previewArtifact(artifact.sha256,artifact.name),'quiet'),
            button('Download',async()=>{
              try{
                const response=await fetch('/api/runs/'+id+'/artifacts/'+artifact.sha256,{headers:{Authorization:'Bearer '+state.token}});
                if(!response.ok)throw new Error('Artifact download failed');
                download(await response.blob(),artifact.name);
              }catch(error){toast(error.message,true);}
            })
          )
        )));
      }

      actions.replaceChildren(...[
        button('Download log',()=>download(new Blob([output],{type:'text/plain'}),id+'.log')),
        !terminal.has(run.status)&&canOperate()?button(run.cancel?'Cancellation requested':'Cancel execution',async()=>{
          await action('/runs/'+id+'/cancel',undefined,'Cancellation requested');
          update();
        },'danger',run.cancel):null
      ].filter(Boolean));

      if(terminal.has(run.status)&&!log.has_more){close();refresh();}
    }catch(error){
      logs.textContent='Could not refresh execution: '+error.message;
    }finally{
      busy=false;
    }
  }

  const timer=setInterval(update,1500);
  await update();
}

function download(blob,name){
  const url=URL.createObjectURL(blob),anchor=el('a',{href:url,download:name});
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

setInterval(()=>{if(state.session&&!document.hidden)refresh();},5000);
