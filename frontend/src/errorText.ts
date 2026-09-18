type Payload={code?:unknown;message?:unknown};

const messages:Record<string,string>={
RECEIPT_CONFLICT:'小票已变化，请刷新记录后重新核对',
RECEIPT_SIZE:'请选择不超过 5 MiB 的非空图片',
RECEIPT_TYPE:'仅支持 PNG 或 JPEG 图片',
RECEIPT_STORAGE:'小票文件暂时无法访问，请重试',
RECEIPT_PARSER_UNAVAILABLE:'自动识别暂不可用，请手工补录',
RECEIPT_PARSER_FAILED:'识别失败，请手工补录或稍后重试',
SHOPPING_CONFLICT:'采购版本或状态已变化，请刷新采购清单',
NO_SHOPPING_NEEDED:'此方案无需补购',
BUDGET_EXCEEDED:'实际采购金额超过方案预算，请修改采购数量或另建方案',
BUDGET_UNKNOWN:'补购预算尚无法核实，请补充价格或修改预算',
CONFIRMATION_EXPIRED:'确认已超过有效期，请取消并重新准备操作',
COOKING_RETRACTED:'这次用餐已经撤销',
SESSION_CONFLICT:'对话已在其他页面更新，请重新打开最新对话',
RUN_BUSY:'请先完成或取消当前运行',
RUN_NOT_READY:'当前运行状态无法继续，本次没有新进展；请查看运行状态，或开始新对话',
RUN_NOT_PENDING:'没有等待确认的操作，请重新准备',
RUN_FINISHED:'本次运行已经结束',
RUN_NOT_RETRYABLE:'本次运行当前无法恢复，请新建对话或取消后重试',
CONTEXT_LIMIT:'对话上下文已达上限，请开始新对话',
STEP_LIMIT:'助手已达到单轮步数上限，继续或恢复都会立即再次超限；请开始新对话',
MODEL_NOT_CONFIGURED:'尚未配置模型，请按后端说明设置模型地址、名称和密钥',
MODEL_UNAVAILABLE:'模型服务暂时不可用，请稍后重试',
MODEL_PROTOCOL_ERROR:'模型应答异常，请稍后重试或改用页面操作',
PLAN_STALE:'方案已过期：库存、日期或偏好发生变化，请更新方案后再确认',
PLAN_CONFLICT:'方案版本或状态已变化，请刷新',
PLAN_INFEASIBLE:'当前条件下此菜谱不可行，请调整方案',
INVALID_CREDENTIALS:'用户名或密码不正确',
USERNAME_TAKEN:'用户名已存在',
UNAUTHENTICATED:'登录已失效，请重新登录',
INSUFFICIENT_STOCK:'可用食材不足，请先补充库存',
BATCH_ARCHIVED:'批次已归档，请先恢复',
VERSION_CONFLICT:'记录已变化，请刷新后重试',
UNIT_AMBIGUOUS:'单位不能直接换算，请核对数量',
QUANTITY_TOO_LARGE:'数量超过可保存范围，请减少数量或分批记录',
VALIDATION_ERROR:'请检查填写内容、数量和单位',
NAME_CONFLICT:'这个食材名称或别名已存在',
DUPLICATE_INGREDIENT:'同一菜谱中食材不能重复，请合并后再保存',
DATABASE_UNAVAILABLE:'暂时无法连接数据库',
MIGRATIONS_PENDING:'数据库正在准备中，请稍后重试',
DATABASE_NOT_READY:'数据库尚未就绪，请稍后重试',
IDEMPOTENCY_CONFLICT:'该请求标识已用于不同内容，请重试本次操作',
EXAMPLE_UNIT_CONFLICT:'已有同名食材使用了不同单位，请先处理后再导入',
NOT_FOUND:'没有找到对应记录',
};

const patterns:{pattern:RegExp;render:(match:RegExpMatchArray)=>string}[]=[
{pattern:/^Review receipt line (\d+) before confirming$/,render:(m)=>`请先核对第 ${m[1]} 项小票内容，再确认入库`},
{pattern:/^Check date and source on receipt line (\d+)$/,render:(m)=>`请核对第 ${m[1]} 项小票的日期与日期来源`},
];

// The server keeps English messages for logs; the UI is code-driven so no unmapped
// text reaches the page verbatim. Line-numbered messages stay identifiable because
// each code has exactly one server message shape.
export function errorText(payload?:Payload|null):string{
 const code=typeof payload?.code==='string'?payload.code:'';
 const message=typeof payload?.message==='string'?payload.message:'';
 for(const entry of patterns)if(entry.pattern.test(message))return entry.render(message.match(entry.pattern) as RegExpMatchArray);
 if(code&&Object.hasOwn(messages,code))return messages[code];
 if(code==='CONFLICT')return '操作发生冲突，请刷新后重试';
 if(code)return '操作未完成，请重试或刷新页面';
 return message||'操作未完成，请重试';
}
