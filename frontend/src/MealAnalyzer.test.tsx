import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import MealAnalyzer from './components/MealAnalyzer';
import { analyzeMeal, calculateMeal } from './mealApi';
import intelligence from './nutritionTestFixture.json';

jest.mock('./mealApi',()=>({analyzeMeal:jest.fn(),calculateMeal:jest.fn()}));
const analyze=analyzeMeal as jest.Mock; const calculate=calculateMeal as jest.Mock;
const proposal={analysis_id:'test',meal_name:'Meal',components:[
  {display_name:'broccoli',confidence:'high',visible_state:null,uncertainty:'Check preparation',normalized_name:'broccoli',identity_status:'recognized'},
  {display_name:'curry',confidence:'low',visible_state:null,uncertainty:'Ingredients hidden',normalized_name:'curry',identity_status:'unresolved'}]};
const result=()=>({analysis_id:'result',basis:'entered_consumed_amounts',nutrition:JSON.parse(JSON.stringify(intelligence))});

test('long manual food remains editable with portion, confirmation and removal controls', () => {
  page();
  const name = 'LongCustomFood'.repeat(8);
  add(name);
  expect(screen.getByLabelText('Food 1')).toHaveValue(name);
  amount('150');
  confirm();
  expect(screen.getByRole('button', { name: 'Calculate nutrition' })).toBeEnabled();
  fireEvent.change(screen.getByLabelText('Food 1'), { target: { value: name + ' raw' } });
  expect(screen.getByRole('button', { name: 'Calculate nutrition' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Remove food 1' }));
  expect(screen.queryByLabelText('Food 1')).not.toBeInTheDocument();
  expect(analyze).not.toHaveBeenCalled();
  expect(calculate).not.toHaveBeenCalled();
});
beforeEach(()=>{jest.resetAllMocks();analyze.mockResolvedValue(proposal);calculate.mockResolvedValue(result());URL.createObjectURL=jest.fn(()=> 'blob:meal');URL.revokeObjectURL=jest.fn();});
const page=()=>render(<MealAnalyzer onNavigate={jest.fn()}/>);
const upload=()=>fireEvent.change(screen.getByLabelText('Upload Meal Photo'),{target:{files:[new File(['photo'],'meal.png',{type:'image/png'})]}});
const add=(name='broccoli')=>{fireEvent.change(screen.getByLabelText('Add a food'),{target:{value:name}});fireEvent.click(screen.getByRole('button',{name:'Add component'}));};
const amount=(value='100',index=1)=>{fireEvent.change(screen.getByLabelText(`Amount eaten ${index}`),{target:{value}});fireEvent.change(screen.getByLabelText(`Unit ${index}`),{target:{value:'g'}});};
const confirm=()=>fireEvent.click(screen.getByRole('button',{name:'Confirm meal'}));
const calc=()=>fireEvent.click(screen.getByRole('button',{name:'Calculate nutrition'}));
const identify=async()=>{upload();fireEvent.click(screen.getByRole('button',{name:'Analyze meal'}));await screen.findByText('Looks like broccoli');};

test('preview has no automatic vision or nutrition and explicit analysis shows uncertainty',async()=>{
  page();upload();expect(screen.getByAltText('Meal preview')).toBeInTheDocument();expect(analyze).not.toHaveBeenCalled();expect(calculate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Analyze meal'}));await screen.findByText('Looks like broccoli');
  expect(screen.getByText(/Not sure - please review curry/)).toBeInTheDocument();expect(screen.getByText(/Name unresolved/)).toBeInTheDocument();
  expect(screen.getByLabelText('Amount eaten 1')).toHaveValue(null);expect(screen.getByLabelText('Unit 1')).toHaveValue('');expect(calculate).not.toHaveBeenCalled();
});
test('signed-out manual workflow requires explicit amounts and confirmation',async()=>{
  page();add();confirm();expect(screen.getByRole('button',{name:'Calculate nutrition'})).toBeDisabled();amount();
  expect(screen.getByRole('button',{name:'Calculate nutrition'})).toBeDisabled();confirm();calc();
  await screen.findByRole('region',{name:'Meal nutrition result'});expect(calculate).toHaveBeenCalledWith([{name:'broccoli',quantity:100,unit:'g'}],expect.anything());expect(analyze).not.toHaveBeenCalled();
  expect(screen.getByText('Complete core nutrient data')).toBeInTheDocument();
});
test('edit remove manual add clears AI confidence and invalidates confirmation',async()=>{
  page();await identify();fireEvent.change(screen.getByLabelText('Food 1'),{target:{value:'spinach'}});expect(screen.queryByText('Looks like broccoli')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Remove food 2'}));add('custom food');amount();amount('200',2);confirm();
  fireEvent.change(screen.getByLabelText('Food 2'),{target:{value:'cheese pizza'}});expect(screen.getByRole('button',{name:'Calculate nutrition'})).toBeDisabled();
});
test('quantity changes immediately clear displayed nutrition and require reconfirmation',async()=>{
  page();add();amount();confirm();calc();await screen.findByRole('region',{name:'Meal nutrition result'});
  fireEvent.change(screen.getByLabelText('Amount eaten 1'),{target:{value:'200'}});expect(screen.queryByRole('region',{name:'Meal nutrition result'})).not.toBeInTheDocument();expect(screen.getByRole('button',{name:'Calculate nutrition'})).toBeDisabled();
});
test('partial and unavailable nutrient data remain honest',async()=>{
  const response=result();response.nutrition.nutrition_status='partial';response.nutrition.calculated_nutrition.totals.calories=null;response.nutrition.calculated_nutrition.known_totals.calories=50;
  response.nutrition.calculated_nutrition.totals.protein=null;response.nutrition.calculated_nutrition.known_totals.protein=0;
  calculate.mockResolvedValue(response);page();add();amount();confirm();calc();await screen.findByText('Partial nutrition data');
  expect(screen.getByText('50 kcal')).toBeInTheDocument();expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0);expect(screen.getAllByText('Partial data').length).toBeGreaterThan(0);
});
test('unavailable nutrition is not fabricated',async()=>{
  const response=result();response.nutrition.nutrition_status='unavailable';Object.keys(response.nutrition.calculated_nutrition.totals).forEach(k=>{response.nutrition.calculated_nutrition.totals[k]=null;response.nutrition.calculated_nutrition.known_totals[k]=null;});
  calculate.mockResolvedValue(response);page();add();amount();confirm();calc();await screen.findByText('Nutrition unavailable');expect(screen.getAllByText('Unknown')).toHaveLength(7);
});
test('vision failure permits manual entry and explicit retry with no fallback',async()=>{
  analyze.mockRejectedValueOnce(new Error('PRIVATE'));page();upload();fireEvent.click(screen.getByRole('button',{name:'Analyze meal'}));await screen.findByRole('alert');expect(screen.queryByLabelText('Food 1')).not.toBeInTheDocument();
  expect(screen.queryByText('PRIVATE')).not.toBeInTheDocument();add();expect(screen.getByLabelText('Food 1')).toHaveValue('broccoli');
  fireEvent.click(screen.getByRole('button',{name:'Analyze meal'}));await screen.findByText('Looks like broccoli');
});
test('empty vision allows manual components',async()=>{
  analyze.mockResolvedValue({...proposal,components:[]});page();upload();fireEvent.click(screen.getByRole('button',{name:'Analyze meal'}));await screen.findByText(/No foods identified/);add('pizza');expect(screen.getByLabelText('Food 1')).toHaveValue('pizza');
});
test('late vision response ignored after replacement',async()=>{
  let finish:any;analyze.mockImplementation(()=>new Promise(r=>{finish=r;}));page();upload();fireEvent.click(screen.getByRole('button',{name:'Analyze meal'}));expect(screen.getByText('Looking at meal components...')).toBeInTheDocument();upload();await act(async()=>finish(proposal));expect(screen.queryByLabelText('Food 1')).not.toBeInTheDocument();expect(analyze.mock.calls[0][1].aborted).toBe(true);
});
test('late nutrition response ignored after amount edit',async()=>{
  let finish:any;calculate.mockImplementation(()=>new Promise(r=>{finish=r;}));page();add();amount();confirm();calc();expect(screen.getByText('Calculating from food data...')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Amount eaten 1'),{target:{value:'250'}});await act(async()=>finish(result()));expect(screen.queryByRole('region',{name:'Meal nutrition result'})).not.toBeInTheDocument();expect(calculate.mock.calls[0][1].aborted).toBe(true);
});
test('remove photo clears components and nutrition',async()=>{
  page();await identify();fireEvent.click(screen.getByRole('button',{name:'Remove'}));expect(screen.queryByLabelText('Food 1')).not.toBeInTheDocument();expect(URL.revokeObjectURL).toHaveBeenCalled();
});
test('unmount cancels pending nutrition',()=>{
  calculate.mockImplementation(()=>new Promise(()=>{}));const view=page();add();amount();confirm();calc();view.unmount();expect(calculate.mock.calls[0][1].aborted).toBe(true);
});
test('nutrition failure supports manual retry',async()=>{
  calculate.mockRejectedValueOnce(new Error('PRIVATE'));page();add();amount();confirm();calc();await screen.findByRole('alert');expect(screen.queryByText('PRIVATE')).not.toBeInTheDocument();calc();await screen.findByRole('region',{name:'Meal nutrition result'});expect(calculate).toHaveBeenCalledTimes(2);
});
test('invalid portions cannot calculate; no Pantry or recipe actions',()=>{
  page();add();amount('0');confirm();expect(screen.getByRole('button',{name:'Calculate nutrition'})).toBeDisabled();expect(screen.queryByRole('button',{name:'Add to Pantry'})).not.toBeInTheDocument();expect(screen.queryByRole('button',{name:/Create recipe/})).not.toBeInTheDocument();
});
test.each(['unit','name','remove','add'])('%s edit invalidates calculated totals',async(change)=>{
  page();add();amount();confirm();calc();await screen.findByRole('region',{name:'Meal nutrition result'});
  if(change==='unit') fireEvent.change(screen.getByLabelText('Unit 1'),{target:{value:'oz'}});
  if(change==='name') fireEvent.change(screen.getByLabelText('Food 1'),{target:{value:'broccoli cooked'}});
  if(change==='remove') fireEvent.click(screen.getByRole('button',{name:'Remove food 1'}));
  if(change==='add') add('rice');
  expect(screen.queryByRole('region',{name:'Meal nutrition result'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Calculate nutrition'})).toBeDisabled();
});
test('cancelled calculation cannot overwrite a later calculation',async()=>{
  let finish:any;calculate.mockImplementationOnce(()=>new Promise(r=>{finish=r;}));
  page();add();amount();confirm();calc();fireEvent.click(screen.getByRole('button',{name:'Cancel'}));calc();
  await screen.findByRole('region',{name:'Meal nutrition result'});
  const old=result();old.nutrition.nutrition_status='unavailable';await act(async()=>finish(old));
  expect(screen.queryByText('Nutrition unavailable')).not.toBeInTheDocument();
});
