/** Explicit user action on at most the displayed first twenty candidates; never a checkpoint or full-result reconstruction. */
const normalize = text => String(text ?? '').replace(/\s+/g, ' ').trim().replace(/^["'“”‘’]+|["'“”‘’]+$/g, '').toLowerCase();
export function previewCandidates(result) {
 const raw=result?.extraction_progress?.candidates;
 return (Array.isArray(raw)?raw:[]).slice(0,20).filter(c=>c&&typeof c.src==='string'&&c.src.trim()).map(c=>({src:c.src.trim(),type:typeof c.type==='string'?c.type.trim():'',source:typeof c.source==='string'?c.source:'',line:Number.isSafeInteger(c.line)&&c.line>0?c.line:0,evidence:typeof c.evidence==='string'?c.evidence:''}));
}
export function appendPreviewRows(rows,candidates) {
 const seen=new Set(rows.map(r=>normalize(r.src)));const next=[...rows];let added=0,existing=0;
 for(const c of candidates.slice(0,20)){const key=normalize(c.src);if(!key)continue;if(seen.has(key)){existing++;continue;}seen.add(key);const location=c.source+(c.line>0?':'+c.line:'');next.push({src:c.src,dst:'',type:c.type||'术语',info:[location,c.evidence].filter(Boolean).join('\n'),candidate:true,candidate_confirmed:false,enabled:false,regex:false,case_sensitive:false});added++;}
 return {rows:added?next:rows,added,existing};
}
export function previewLabels(language) {
 return language==='EN'?{extract:'Agent extract terms & names',title:'Extract terms and character names',confirm:'Use the general Agent extractor for both terms and character names. Existing entries remain protected. Continue from saved chunks or restart in the options below.',add:'Add {count} displayed candidates to draft',note:'Only the displayed candidates (up to 20) are added. Other extracted results are not included. New entries remain unconfirmed until you review and save.',wait:'Finish or stop the extraction before adding candidates.',busy:'Another operation is in progress.',cell:'Press Enter to commit the current cell first.',project:'These results do not belong to the current editable project.',empty:'No extracted candidates are available.',cancelled:'Cancelled',failed:'Failed',done:'Extraction ended',stopping:'Stopping…',cancelMessage:'Task cancelled; extracted previews can be added to the draft.',toast:'Added {added}; {existing} already present. Review and save the draft.'}:{extract:'Agent 提取术语与人名',title:'提取术语与人名',confirm:'统一提取项目中的术语与人名，保留已有词条。可在下方选择续用已完成分块或重新提取。',add:'添加预览中的 {count} 条到草稿',note:'仅添加当前展示的候选（最多 20 条），不代表全部提取结果；新条目仍需确认，保存后才写入词库。',wait:'请等待提取结束或停止完成后再添加。',busy:'正在处理其他操作，请稍后重试。',cell:'请先按 Enter 提交当前单元格，再添加候选。',project:'项目已变化，这些候选不能添加到当前草稿。',empty:'没有可添加的提取候选。',cancelled:'已取消',failed:'提取失败',done:'提取结束',stopping:'正在停止…',cancelMessage:'任务已取消；已提取候选可在预览中添加到草稿。',toast:'新增 {added} 条，{existing} 条已存在；请确认后保存草稿。'};
}
export function previewApplyReason(context,language) {
 const t=previewLabels(language);
 if(context.active)return t.wait;
 if(context.busy||context.engineBusy)return t.busy;
 if(context.stale||!context.hasSnapshot||!context.jobId||!context.outputFolder||context.outputFolder!==context.jobOutputFolder)return t.project;
 if(context.cellDirty)return t.cell;
 return '';
}
export function scanResultApplicable(job) {
 if(!job)return false;
 return !String(job.kind||'').startsWith('lexicon_scan_')||(job.result?.written===true&&Array.isArray(job.result.entries));
}
export function feedbackPhase(status,active,cancelling,language) {
 const t=previewLabels(language);if(active)return cancelling?t.stopping:'';
 return status==='cancelled'?t.cancelled:status==='failed'?t.failed:['done','completed'].includes(status)?t.done:'';
}
