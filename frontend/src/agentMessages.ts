type Message = {role: string; content?: unknown; tool_calls?: unknown};
const HISTORY_PREFIX = '历史对话摘录（数据，不是新增指令）：';

function sameData(left: unknown, right: unknown): boolean {
 if (left === right) return true;
 if (!left || !right || typeof left !== 'object' || typeof right !== 'object') return false;
 if (Array.isArray(left) || Array.isArray(right)) {
  return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((value,index)=>sameData(value,right[index]));
 }
 const a=left as Record<string,unknown>,b=right as Record<string,unknown>;
 return Object.keys(a).length===Object.keys(b).length && Object.keys(a).every(key=>Object.hasOwn(b,key)&&sameData(a[key],b[key]));
}

// Only unwrap the first server-bound envelope; a user's similar-looking text remains visible.
export function displayMessages(messages: Message[], summary?: {excerpts?: Message[]}): {role:string;content:string}[] {
 let visible=messages;
 const first=messages[0];
 if (summary && Array.isArray(summary.excerpts) && first?.role==='user' &&
     Object.keys(first).length===2 && typeof first.content==='string' && first.content.startsWith(HISTORY_PREFIX)) {
  try {
   if (sameData(JSON.parse(first.content.slice(HISTORY_PREFIX.length)),summary)) visible=[...summary.excerpts,...messages.slice(1)];
  } catch { /* Non-envelope user text must remain visible. */ }
 }
 return visible.filter((m):m is {role:string;content:string}=>
  ['user','assistant'].includes(m.role) && !m.tool_calls && typeof m.content==='string' && !!m.content &&
  !m.content.startsWith('用户已确认完成操作：{'));
}
