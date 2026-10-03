import { analyzeIngredients } from './visionApi';
const file=new File(['photo'],'photo.png',{type:'image/png'});
beforeEach(() => { global.fetch=jest.fn(); });
test('vision client sends raw image to backend only without account/provider credentials', async () => {
  (fetch as jest.Mock).mockResolvedValue({ok:true,json:async () => ({analysis_id:'id',detections:[]})});
  await analyzeIngredients(file,new AbortController().signal);
  expect((fetch as jest.Mock).mock.calls[0][0]).toMatch(/\/api\/vision\/ingredients$/);
  expect((fetch as jest.Mock).mock.calls[0][1].headers).toEqual({'Content-Type':'image/png'});
  expect((fetch as jest.Mock).mock.calls[0][1].body).toBe(file);
});
test('vision client sanitizes provider error bodies', async () => {
  (fetch as jest.Mock).mockResolvedValue({ok:false,status:503,json:async () => ({error:'PRIVATE'})});
  await expect(analyzeIngredients(file,new AbortController().signal)).rejects.toThrow('unavailable');
});
test('vision client rejects malformed suggestions', async () => {
  (fetch as jest.Mock).mockResolvedValue({ok:true,json:async () => ({analysis_id:'id',detections:[{confidence:'.93'}]})});
  await expect(analyzeIngredients(file,new AbortController().signal)).rejects.toThrow('could not be read');
});
test('vision client forwards cancellation', async () => {
  const controller=new AbortController();
  (fetch as jest.Mock).mockImplementation((_url,options) => new Promise((_resolve,reject) => options.signal.addEventListener('abort',() => reject(new Error('abort')))));
  const pending=analyzeIngredients(file,controller.signal); controller.abort();
  await expect(pending).rejects.toThrow('cancelled');
});
