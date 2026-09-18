type ReceiptLine={quantity:string|null;unit:string|null;ingredient_id:string|null;excluded:boolean};
type Ingredient={id:string;unit:string};
const dimensions:Record<string,string>={g:'mass',kg:'mass',ml:'volume',l:'volume',piece:'count'};
const labels:Record<string,string>={g:'克',kg:'千克',ml:'毫升',l:'升',piece:'个'};

export function receiptUnitProblem(line:ReceiptLine,items:Ingredient[]):string|null{
 if(line.excluded)return null;
 const ingredient=items.find(item=>item.id===line.ingredient_id);
 if(!ingredient||!line.unit||!line.quantity)return null;
 if(!dimensions[line.unit]||dimensions[line.unit]!==dimensions[ingredient.unit]){
  return `小票单位为“${labels[line.unit]||line.unit}”，对应食材按“${labels[ingredient.unit]||ingredient.unit}”记录，不能直接换算。请核对对应食材，或填写实际测量的数量和单位；不要只替换单位。`;
 }
 const quantity=Number(line.quantity);
 if(!Number.isFinite(quantity)||quantity<=0)return '入库数量必须大于 0。';
 if(line.unit==='piece'&&!Number.isInteger(quantity))return '按个入库时，数量必须为整数。';
 return null;
}
