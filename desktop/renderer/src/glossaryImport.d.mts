export interface ImportedTerm {src:string;dst:string;type:string;info:string;case_sensitive:boolean;regex:boolean}
export interface ImportMergeResult<Row> {rows:Row[];added:number;duplicate:number;kept:number;filled:number;replaced:number}
export function normalizeImportRows(data:unknown):{rows:ImportedTerm[];error:string};
export function mergeImportedRows<Row extends {src:string}>(current:readonly Row[],incoming:readonly {src:string}[],strategy:'keep'|'fill'|'overwrite'):ImportMergeResult<Row>;
export function importMergeLabels(language?:string|null):Record<string,string>;
