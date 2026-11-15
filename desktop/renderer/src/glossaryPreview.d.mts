export interface PreviewCandidate {src:string;type:string;source:string;line:number;evidence:string}
export interface PreviewDraftRow {src:string;dst:string;[key:string]:unknown}
export interface PreviewContext {active:boolean;busy:boolean;engineBusy:boolean;stale:boolean;hasSnapshot:boolean;cellDirty:boolean;jobId?:string;outputFolder?:string;jobOutputFolder?:string}
export function previewCandidates(result:unknown):PreviewCandidate[];
export function appendPreviewRows(rows:PreviewDraftRow[],candidates:PreviewCandidate[]):{rows:PreviewDraftRow[];added:number;existing:number};
export function previewLabels(language?:string|null):Record<string,string>;
export function previewApplyReason(context:PreviewContext,language?:string|null):string;
export function scanResultApplicable(job:unknown):boolean;
export function feedbackPhase(status:string|undefined,active:boolean,cancelling:boolean,language?:string|null):string;
