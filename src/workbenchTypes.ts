export type MetricGroup = {count:number; MRR:number|null; 'NDCG@5':number|null; 'NDCG@10':number|null; 'Recall@5':number|null; 'Recall@10':number|null; article_coverage:number|null; exposure_hhi:number|null};
export type Metrics = {overall:MetricGroup;cold:MetricGroup};
export type ModelResult = {id:string;status:string;reused:boolean;metrics:Metrics|null;identity:Record<string,string>|null;jobs:{id:string;state:string;created:number;finished:number|null;error:string|null}[];epochs:{epoch:number;loss:number}[];failure:unknown;description:string|null};
export type Experiment = {id:string;title:string;status:string;historical:boolean;created:number;instruction?:string;candidate_limit:number;error?:string|null;models:ModelResult[];selection:{selected:string}|null;protocol:string;counts:{train:number;validation:number};session_id:string|null;event_seq:number;usage:{requests:number;confirmed_responses:number;missing_usage_requests:number;tokens:{input_tokens:number;output_tokens:number;total_tokens:number}|null;estimated_credits:{used:number;source:string}|null;cost:null};heldout:{variant:string;metrics:Metrics}[]|null};
export type ExperimentList = Pick<Experiment,'id'|'title'|'status'|'historical'|'created'|'candidate_limit'>;
export type Article = {id:string;title:string;abstract:string;category:string;subcategory:string;cold:boolean};
export type RankedArticle=Article & {rank:number;score:number;clicked:boolean};
export type Case = {id:string;index:number;positive:Article;history:Article[];baseline:RankedArticle[];candidate:RankedArticle[]};
export type CaseList = {total:number;items:{index:number;id:string;title:string;cold:boolean;candidate_count:number}[]};
export type DistributionArticle=Article & {baseline:number;candidate:number;delta:number};
export type Distribution={items:DistributionArticle[];case_count:number;catalogue_count:number;definition:string};
export type ExecutionEvent={seq:number;source:string;time:number;kind:string;title:string;payload:Record<string,unknown>};
export type Health={product:string;api:string;data:string;sandbox:string;agh_build:string;active:string|null;model:string};
export async function api<T>(path:string,init?:RequestInit):Promise<T>{
 const res=await fetch('/api'+path,{...init,headers:{'Content-Type':'application/json',...init?.headers}});
 if(!res.ok){const body=await res.json().catch(()=>({detail:'服务暂时不可用'}));throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail));}
 return res.json() as Promise<T>;
}
