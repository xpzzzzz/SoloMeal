export const units:Record<string,string>={g:'克',kg:'千克',ml:'毫升',l:'升',piece:'个'};
const titles:Record<string,string>={attention:'优先处理',recommendations:'今天推荐',shopping:'待采购',recent:'最近做过'};
export const HOME_SECTIONS=['attention','recommendations','shopping','recent'] as const;
export const READ_ONLY_SECTIONS=['attention','shopping','recent'] as const;
export const sectionTitle=(name:string):string=>titles[name]||'这一栏';
const count=(value:unknown):number=>{const n=Number(value);return Number.isFinite(n)?n:0;};

// A missing day count means no date was recorded, which is not the same as "today".
export function dayText(days:unknown):string{
 if(days===null||days===undefined||days==='')return '到期日期未知';
 const n=Number(days);
 if(!Number.isFinite(n))return '到期日期未知';
 if(n<0)return `已过期 ${-n} 天`;
 if(n===0)return '今天到期';
 if(n===1)return '明天到期';
 return `${n} 天后到期`;
}

export function expiryTag(state:unknown):string{return state==='expired'?'已过期，需检查':'三天内到期';}

export function quantityText(quantity:unknown,unit:string):string{
 return `${quantity===null||quantity===undefined||quantity===''?'—':String(quantity)} ${units[unit]||unit}`;
}

export function attentionText(row:any):string{
 return `${row?.name||'未知食材'} · ${quantityText(row?.quantity,row?.unit)} · ${row?.expires_on||'未填写'} ${dayText(row?.days_left)}`;
}

export function attentionSummary(data:any):string{
 const total=count(data?.total_count),shown=count(data?.items?.length);
 if(!total)return '';
 const parts=[`共 ${total} 项需要处理：已过期 ${count(data?.expired_count)} 项，三天内到期 ${count(data?.expiring_count)} 项`];
 if(total>shown)parts.push(`此处按日期只列最近 ${shown} 项`);
 return parts.join('；')+'。';
}

// A saved duration is always 1..480; anything else is missing rather than zero minutes.
export function minutesText(value:unknown):string{
 const n=Number(value);
 return typeof value==='number'&&Number.isInteger(n)&&n>0?`${n} 分钟`:'未记录用时';
}

export function shoppingText(list:any):string{
 const pending=count(list?.pending_count);
 return `${list?.recipe_name||'未命名采购'} · ${pending>0?`待买 ${pending} 项`:'已勾选，待入库'} · 共 ${count(list?.items_count)} 项`;
}

export function shoppingSummary(data:any):string{
 const lists=count(data?.list_count);
 if(!lists)return '';
 const parts=[`${lists} 张清单未处理，共 ${count(data?.pending_total)} 项待买`];
 if(lists>count(data?.items?.length))parts.push('此处只显示最近 '+count(data?.items?.length)+' 张');
 return parts.join('，')+'。';
}

export function recentText(row:any):string{
 return `${row?.recipe_name||'未命名菜谱'} · ${row?.cooked_on||'日期未知'} · ${count(row?.servings)} 人份 · ${minutesText(row?.actual_minutes)}`;
}

export function recentSummary(data:any):string{
 const completed=count(data?.completed_count);
 if(!completed)return '';
 return `累计完成 ${completed} 餐`+(completed>count(data?.items?.length)?`，此处只显示最近 ${count(data?.items?.length)} 餐`:'')+'。';
}

export function emptyText(name:string):string{
 return ({
  attention:'三天内没有需要处理的食材。',
  recommendations:'还没有符合条件的菜谱，可以先发现菜谱或录入一道。',
  shopping:'没有待办采购清单。缺料时会自动出现在这里。',
  recent:'还没有完成的用餐记录。',
 } as Record<string,string>)[name]||'这里暂时没有内容。';
}
