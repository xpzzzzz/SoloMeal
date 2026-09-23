export type Timer = {accumulated_ms:number;running_since_ms:number|null;state:'running'|'paused'};
export function elapsed(t:Timer,now=Date.now()){return t.accumulated_ms+(t.state==='running'?Math.max(0,now-(t.running_since_ms??now)):0);}
export function pause(t:Timer,now=Date.now()):Timer{return {accumulated_ms:elapsed(t,now),running_since_ms:null,state:'paused'};}
export function resume(t:Timer,now=Date.now()):Timer{return {...t,running_since_ms:now,state:'running'};}
export function defaultMinutes(ms:number){return Math.max(1,Math.ceil(ms/60000));}
export const timerPrefix=(user:string)=>'solomeal:cooking:'+user+':';
export function clearTimers(user:string){try{for(const key of Object.keys(localStorage))if(key.startsWith(timerPrefix(user)))localStorage.removeItem(key);}catch{/* Storage may be disabled; session state is still cleared. */}}

// Decimal arithmetic mirrors server ROUND_CEILING without float boundary errors.
export function scaledQuantity(quantity:string,servings:number,base:number,unit:string){
 const [whole,fraction='']=quantity.split('.');const scale=10n**BigInt(fraction.length);
 const value=BigInt(whole)*scale+BigInt(fraction||'0');const precision=unit==='piece'?1n:1000n;
 const numerator=value*BigInt(servings)*precision,denominator=scale*BigInt(base);
 const rounded=(numerator+denominator-1n)/denominator;
 return unit==='piece'?String(rounded):String(rounded/1000n)+'.'+String(rounded%1000n).padStart(3,'0');
}
