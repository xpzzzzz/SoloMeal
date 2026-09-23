export type DraftLine={name?:string|null;quantity?:string|null;unit?:string|null;optional?:boolean};
export type Ingredient={id:string;name:string;unit:string};
export type Issue=Record<string,unknown>&{field?:unknown;code?:unknown};

const base:Record<string,string>={g:'g',kg:'g',ml:'ml',l:'ml',piece:'piece'};
const unitName:Record<string,string>={g:'克',kg:'千克',ml:'毫升',l:'升',piece:'个'};
const sectionName:Record<string,string>={name:'菜谱名称',servings:'人数',minutes:'用时',equipment:'厨具',
 steps:'做法步骤',ingredients:'食材清单',cooking_methods:'烹饪方式标签'};

// The server addresses every problem by field path; the page only ever renders the
// Chinese label, so an unmapped code cannot leak English text or a raw path.
export function fieldText(field:string):string{
 const part:Record<string,string>={name:'名称',quantity:'数量',unit:'单位',resolved_ingredient_id:'所选食材'};
 const line=/^ingredients\[(\d+)\]\.(name|quantity|unit|resolved_ingredient_id)$/.exec(field);
 if(line)return `第 ${Number(line[1])} 项食材的${part[line[2]]}`;
 const item=/^ingredients\[(\d+)\]$/.exec(field);
 if(item)return `第 ${Number(item[1])} 项食材`;
 const step=/^steps\[(\d+)\]$/.exec(field);
 if(step)return `第 ${Number(step[1])} 步`;
 return sectionName[field]||'填写内容';
}

function text(issue:Issue,key:string){const value=issue[key];return typeof value==='string'||typeof value==='number'?String(value):'';}
function number(issue:Issue,key:string){return typeof issue[key]==='number'?issue[key]:undefined;}

export function issueText(issue:Issue):string{
 const field=fieldText(text(issue,'field'));
 const value=text(issue,'value');
 switch(issue.code){
  case 'value_missing':return `请填写${field}。`;
  case 'value_not_integer':return `${field}需要整数${value?`，目前是“${value}”`:''}。`;
  case 'value_out_of_range':return `${field}需要在 ${number(issue,'minimum')}～${number(issue,'maximum')} 之间${value?`，目前是“${value}”`:''}。`;
  case 'count_out_of_range':return `${field}需要 ${number(issue,'minimum')}～${number(issue,'maximum')} 项${value?`，目前有 ${value} 项`:''}。`;
  case 'value_too_long':return `${field}不能超过 ${number(issue,'maximum')} 字。`;
  case 'unit_missing':return `${field}还缺单位。`;
  case 'unit_invalid':return `${field}的“${value}”不是可用单位，只能填 克 / 千克 / 毫升 / 升 / 个。`;
  case 'quantity_missing':return `${field}还没有数量，请填写实际用量。`;
  case 'quantity_invalid':return `${field}需要大于 0 的数字${value?`，目前是“${value}”`:'，例如“适量”不能用'}。`;
  case 'quantity_too_large':return `${field}超过可保存范围，请减少数量。`;
  case 'quantity_precision':return `${field}最多保留三位小数。`;
  case 'quantity_not_whole':return `${field}按“个”计数时必须是整数。`;
  case 'duplicate_ingredient':return `第 ${Number(text(issue,'other_line')||0)} 项已使用同一种食材${text(issue,'detail')==='optional_conflict'?'，且必需／可选标记不一致':''}，请先合并这两行。`;
  case 'required_ingredient_missing':return '至少要有一种不是可选的食材。';
  case 'unit_dimension_conflict':return `${field}的单位与已有食材不在同一量纲（该食材按${unitName[text(issue,'expected')]||text(issue,'expected')}记录）。请改这一行的单位或换选食材，已有食材的单位不会被改动。`;
  case 'ingredient_unavailable':return `${field}不属于当前账号，请改用本页食材库中的食材。`;
  case 'constraint_mismatch':{
   const detail=text(issue,'detail');
   if(detail==='time_limit')return `本次最多用时 ${number(issue,'maximum')} 分钟，这一道超出，请改用时或修改本次条件。`;
   if(detail==='servings_mismatch')return `本次人数为 ${number(issue,'expected')} 人，这一道不符，请改人数或修改本次条件。`;
   if(detail==='missing_equipment')return `这些厨具不在本次条件内：${(Array.isArray(issue.values)?issue.values:[]).join('、')}。请改用已有厨具，或修改本次条件。`;
   if(detail==='excluded_ingredient')return '这一项在你设定的忌口里，忌口不会被模型覆盖，请删除该行或换食材。';
   return `${field}不符合本次发现条件，请修正后再确认。`;
  }
  case 'step_equipment_unlisted':return `做法里用到了“${value}”，但厨具清单没有列出它。请补上厨具，或确认已核对。`;
  case 'step_ingredient_unlisted':return `做法里出现了“${value}”，但食材清单没有列出它。请补上这一项，或确认已核对。`;
  case 'duplicate_recipe_name':return '菜谱库里已有同名菜谱。确认后会另存一道同名菜谱，请核对是否重复。';
  case 'cooking_method_invalid':return `${field}里的“${value}”不是可选的烹饪方式，请改用列表中的标签。`;
  case 'cooking_method_duplicate':return `${field}“${value}”重复选择，请去掉多余的一项。`;
  default:return `${field}需要检查。`;
 }
}

export function groupByField(issues:Issue[]):Record<string,Issue[]>{
 const grouped:Record<string,Issue[]>={};
 for(const issue of issues){
  const field=text(issue,'field');
  (grouped[field]=grouped[field]||[]).push(issue);
 }
 return grouped;
}

// Mirrors the server's rule closely enough to warn before saving; acceptance stays authoritative.
export function newIngredientHints(lines:DraftLine[],items:Ingredient[]):{name:string;unit:string}[]{
 const known=new Set(items.map(i=>i.name.trim().toLowerCase()));
 const byKey=new Map<string,{name:string;units:Set<string>}>();
 for(const line of lines){
  const name=(line.name||'').trim();
  if(!name||known.has(name.toLowerCase()))continue;
  const key=name.toLowerCase();
  const entry=byKey.get(key)||{name,units:new Set<string>()};
  const baseUnit=base[(line.unit||'').trim().toLowerCase()];
  if(baseUnit)entry.units.add(unitName[baseUnit]);
  byKey.set(key,entry);
 }
 return [...byKey.values()].map(x=>({name:x.name,unit:x.units.size===1?[...x.units][0]
  :x.units.size>1?'互相冲突':'待填写'}));
}
