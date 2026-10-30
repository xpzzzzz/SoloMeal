import React from 'react';

export function WhyRow({why,hint,onSuppress,disabled}:{why:string;hint:string;onSuppress?:()=>void;disabled:boolean}){
 return <details className="proactive-why"><summary title="根据当前库存或采购草稿计算">为什么是现在</summary>
  <p>{why}</p>{onSuppress&&<button className="text-button" disabled={disabled} onClick={onSuppress}>{hint}</button>}</details>;
}
