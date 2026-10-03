import { analyzeMeal, calculateMeal } from './mealApi';
import intelligence from './nutritionTestFixture.json';
beforeEach(()=>{global.fetch=jest.fn();});
test('meal vision uses backend binary transport with no nutrition or credentials',async()=>{
  (fetch as jest.Mock).mockResolvedValue({ok:true,json:async()=>({analysis_id:'id',meal_name:null,components:[]})});
  const file=new File(['photo'],'meal.png',{type:'image/png'});
  await analyzeMeal(file,new AbortController().signal);
  expect((fetch as jest.Mock).mock.calls[0][0]).toMatch(/\/api\/vision\/meal$/);
  expect((fetch as jest.Mock).mock.calls[0][1].body).toBe(file);
  expect((fetch as jest.Mock).mock.calls[0][1].headers).toEqual({'Content-Type':'image/png'});
});
test('meal nutrition sends confirmed structured amounts, never image or model estimates',async()=>{
  (fetch as jest.Mock).mockResolvedValue({ok:true,json:async()=>({analysis_id:'id',basis:'entered_consumed_amounts',nutrition:intelligence})});
  const components=[{name:'broccoli',quantity:200,unit:'g'}];
  await calculateMeal(components,new AbortController().signal);
  const [url,options]=(fetch as jest.Mock).mock.calls[0];
  expect(url).toMatch(/\/api\/nutrition\/meal$/);expect(JSON.parse(options.body)).toEqual({confirmed:true,components});
  expect(options.headers).toEqual({'Content-Type':'application/json'});
});
test('invalid nutrition cannot render as calculated data',async()=>{
  (fetch as jest.Mock).mockResolvedValue({ok:true,json:async()=>({analysis_id:'id',basis:'entered_consumed_amounts',nutrition:{calories:500}})});
  await expect(calculateMeal([],new AbortController().signal)).rejects.toThrow('could not be read');
});
test('meal vision rejects numerical confidence and schema mismatch',async()=>{
  (fetch as jest.Mock).mockResolvedValue({ok:true,json:async()=>({analysis_id:'id',meal_name:'meal',components:[{display_name:'food',confidence:99}]})});
  await expect(analyzeMeal(new File(['x'],'photo.png',{type:'image/png'}),new AbortController().signal)).rejects.toThrow('could not be read');
});
