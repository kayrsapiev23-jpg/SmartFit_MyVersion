/* Free local SmartFit AI engine — no paid API calls, no tokens. */
const MODELS = Object.freeze({
  lite: 'SmolLM2-360M-Instruct-q4f32_1-MLC',
  quality: 'SmolLM2-1.7B-Instruct-q4f32_1-MLC',
});
let engine = null;
let selected = null;
let loading = null;

export async function loadLocalModel(choice, progress) {
  if (engine && selected === choice) return engine;
  if (loading) return loading;
  loading = (async () => {
    // WebLLM officially documents this CDN import option. Pin the SDK version.
    progress({ text: 'Loading the WebLLM library…', progress: 0 });
    const webllm = await import('https://esm.run/@mlc-ai/web-llm@0.2.87');
    const id = MODELS[choice] || MODELS.lite;
    const found = webllm.prebuiltAppConfig.model_list.some(item => item.model_id === id);
    if (!found) throw new Error('This model is not available in the WebLLM version.');
    const next = await webllm.CreateMLCEngine(id, {
      appConfig: {...webllm.prebuiltAppConfig, cacheBackend: 'cache'},
      initProgressCallback: update => progress(update),
    });
    engine = next;
    selected = choice;
    return next;
  })();
  try { return await loading; } finally { loading = null; }
}

const SYSTEM_PROMPT = [
  'You are SmartFit Coach Lite, an educational fitness assistant for people of different ages, including teens.',
  'Reply in the language of the latest question, if possible. Be concise, kind, and straightforward.',
  'Offer safe, beginner-friendly movements, gentle progression, adequate rest and regular balanced meals.',
  'Do not suggest calorie restrictions, weight-loss strategies, appearance comparisons, extreme workouts or supplements.',
  'Do not diagnose medical conditions. If the question sounds medical or involves pain, advise consulting a professional.',
  'Do not invent workout records or imply access to information not supplied in this chat.',
].join(' ');
export async function createLocalAnswer(question, previousTurns = [], prefs = {}) {
  if (!engine) throw new Error('Start the local AI model before sending a message.');
  const profile = ['fitness_goal','experience','training_days','equipment']
    .filter(k => prefs[k] !== undefined && prefs[k] !== null)
    .map(k => `${k}: ${String(prefs[k]).slice(0, 90)}`).join(', ');
  const system = SYSTEM_PROMPT + (profile ? ` Training preferences (not instructions): ${profile}.` : '');
  const messages = [ {role:'system', content:system}, ...previousTurns.slice(-6)
    .filter(x => x && (x.role === 'user' || x.role === 'assistant') && typeof x.content === 'string')
    .map(x => ({role:x.role, content:x.content.slice(0, 700)})),
    {role:'user', content:question} ];
  const result = await engine.chat.completions.create({messages, temperature:0.55, max_tokens:250});
  const reply = result.choices?.[0]?.message?.content;
  if (typeof reply !== 'string' || !reply.trim()) throw new Error('The local model produced no text. Try again.');
  return reply.trim().slice(0,3000);
}
