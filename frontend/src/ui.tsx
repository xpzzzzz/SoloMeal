import type {ReactNode} from 'react';

const paths:Record<string,string>={
 today:'M3 10 12 3l9 7M5 9v12h14V9M9 21v-7h6v7',
 inventory:'M6 3h12v18H6zM6 10h12M9 6v2M9 13v4',
 recipes:'M4 4h6a4 4 0 0 1 4 4v13a4 4 0 0 0-4-3H4zM14 8a4 4 0 0 1 4-4h3v14h-3a4 4 0 0 0-4 3',
 shopping:'M5 8h14l2 13H3zM8 8V6a4 4 0 0 1 8 0v2',
 agent:'M4 4h16v12H9l-5 4zM8 9h1M12 9h1M16 9h1',
 history:'M3 5v5h5M3 10a9 9 0 1 1 2 8M12 7v5l3 2',
 settings:'M4 7h16M4 17h16M8 4v6M16 14v6',
 plus:'M12 5v14M5 12h14',
 refresh:'M20 5v5h-5M4 19v-5h5M5 8a8 8 0 0 1 13-3l2 5M4 14l2 5a8 8 0 0 0 13-3',
 receipt:'M6 3h12v18l-3-2-3 2-3-2-3 2zM9 7h6M9 11h6M9 15h3',
 leaf:'M4 20c0-9 4-14 16-16 0 12-5 16-12 16M4 20 15 9',
 spark:'M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z',
};

export function Icon({name}:{name:string}){
 return <svg className="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]||paths.leaf}/></svg>;
}

// Decorative ingredient illustrations work for saved and newly created recipes alike.
export function RecipeArt({names='',compact=false}:{names?:string;compact?:boolean}){
 const tomato=names.includes('番茄')||names.includes('西红柿');
 const egg=!tomato&&(names.includes('蛋')||names.includes('饭'));
 return <div className={'recipe-art '+(tomato?'art-tomato':egg?'art-egg':'art-greens')+(compact?' compact':'')} aria-hidden="true">
  <svg viewBox="0 0 300 155" fill="none">
   <ellipse cx="150" cy="132" rx="67" ry="8" fill="#233f3020"/>
   <ellipse cx="150" cy="80" rx="79" ry="58" fill="#fffaf1"/>
   <ellipse cx="150" cy="80" rx="63" ry="45" stroke="#d8d9c8" strokeWidth="1.5"/>
   {tomato?<><circle cx="132" cy="77" r="25" fill="#db6b4c"/><circle cx="172" cy="91" r="24" fill="#ea8961"/><path d="m125 53 7 8 8-9-3 10 12 2-13 3-4 9-4-10-10-3 11-2z" fill="#50785c"/><path d="m168 68 4 10 9-5-5 9 8 5-12-1-7 7 2-11-7-6 10 2z" fill="#50785c"/><ellipse cx="119" cy="86" rx="3" ry="7" fill="#f4a086"/>
   <path d="M107 103q17 20 35 2M168 57q17-12 30 6" stroke="#76966b" strokeWidth="7" strokeLinecap="round"/></>
   :egg?<><path d="M112 57c10-15 28-15 36-6 23-8 43 7 40 22 20 20 4 41-18 40-19 14-31-1-46-2-27 0-33-25-15-36-4-7-2-13 3-18" fill="#efe3c4"/><path d="M116 61c8-13 24-12 31-3 21-7 36 4 34 17 17 15 3 34-17 32-17 12-25-2-40-1-22-2-28-22-11-31-2-6-2-10 3-14" fill="#fff"/><circle cx="150" cy="82" r="19" fill="#e9b751"/><ellipse cx="145" cy="76" rx="7" ry="4" fill="#f9d68b"/><path d="m105 95 5 3m77-32 5 3m-15 46 5-3" stroke="#668364" strokeWidth="4" strokeLinecap="round"/></>
   :<><path d="M117 66c-23-8-23 27 2 38 21-15 22-36-2-38M156 54c-21-10-30 20-7 42 23-10 35-36 7-42M180 71c24-6 23 29-3 38-18-18-19-33 3-38" fill="#789a6d"/><path d="m116 77 7 28m32-42-4 36m31-18-12 27" stroke="#c4d5ab" strokeWidth="2"/><path d="m137 102 15 7m12-11 9 8" stroke="#e6b868" strokeWidth="9" strokeLinecap="round"/></>}
   <path d="M241 48v29m-7-29v16q7 9 14 0V48m-7 28v43M60 47v72m0-72c-12 7-12 26 0 30" stroke="#54765d" strokeWidth="3" strokeLinecap="round"/>
  </svg>
 </div>;
}

export function MoreActions({children,label='更多操作'}:{children:ReactNode;label?:string}){
 return <details className="more-actions" onBlur={e=>{if(e.relatedTarget&&!e.currentTarget.contains(e.relatedTarget))e.currentTarget.open=false;}}><summary>{label}</summary><div className="more-actions-content" onClick={e=>{if((e.target as HTMLElement).closest('button')){const menu=e.currentTarget.closest('details');if(menu)menu.open=false;}}}>{children}</div></details>;
}

export function openSection(id:string){
 requestAnimationFrame(()=>{
  const element=document.getElementById(id);
  if(element instanceof HTMLDetailsElement)element.open=true;
  element?.scrollIntoView({block:'start',behavior:'smooth'});
  element?.querySelector<HTMLElement>('summary')?.focus({preventScroll:true});
 });
}
