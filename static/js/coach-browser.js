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

// Training preferences and completed workouts are received from SmartFit's
// authenticated /api/coach/history endpoint. This is app data, not model memory.
const SYSTEM_PROMPT = [
  'You are SmartFit Coach Lite, a helpful fitness education assistant for users including teenagers.',
  'The current user\'s saved preferences and logged workout records are supplied in the next user message.',
  'These records come from SmartFit. You CAN use the supplied records and should not deny access to them.',
  'Do not assume access to information not explicitly supplied, and do not invent workout history.',
  'Answer the question directly in its language if possible, using the supplied preferences.',
  'Recommend safe, moderate activity, technique, rest, balanced nutrition and gradual progress.',
  'Never encourage restrictive eating, weight-loss targets, unsafe supplements or excessive exercise.',
  'Do not diagnose medical conditions. For persistent pain recommend qualified medical advice.',
].join(' ');

function profileSummary(prefs) {
  const result=[];
  for (const [key,label] of [
    ['fitness_goal','Fitness goal'], ['experience','Training experience'],
    ['training_days','Training days per week'], ['equipment','Available equipment']
  ]) {
    const value=prefs?.[key];
    if (value!==undefined && value!==null && String(value).trim())
      result.push(`${label}: ${String(value).slice(0,90)}`);
  }
  if (Number.isFinite(Number(prefs?.workout_count)))
    result.push(`Total logged workout sessions: ${Math.max(0,Number(prefs.workout_count))}`);
  const rows=Array.isArray(prefs?.recent_workouts)?prefs.recent_workouts.slice(0,5):[];
  if(rows.length) {
    result.push('Most recent logged sessions:');
    rows.forEach(r=>result.push(`- ${String(r.date||'').slice(0,20)}: ${String(r.title||'').slice(0,100)}`));
  } else if (prefs?.workout_count===0) result.push('No logged workout sessions yet.');
  return result;
}

const hasNoAccessClaim=text=>/\b(?:i (?:do not|don't|cannot|can't) (?:have (?:the )?(?:ability|access)|access|see)|no access to your (?:personal|fitness)|i'm unable to access)\b|(?:нет доступа|не имею доступа|не могу получить доступ|не вижу ваши данные)/i.test(text);
const looksLikeProfileQuestion=q=>/(?:my|мо[иёя]|менің|менин|у меня|менде).{0,35}(?:goal|fitness|equip|experience|workout|progress|цел|оборуд|трениров|мақсат|жаттығ|жабдық)/i.test(q)
  || /(?:what|какие|какая|какой|қандай).{0,35}(?:goals?|preferences?|оборудован|трениров|мақсат)/i.test(q);

function factualProfileAnswer(prefs) {
  const items=profileSummary(prefs);
  if (!items.length || items.every(x=>/^Total logged|^No logged/.test(x))) return null;
  return `Here's what you saved in your SmartFit profile and workout tracker:\n${items.map(x=>x.startsWith('- ')?x:'• '+x).join('\n')}\n\nI can use these details when discussing a workout routine. If you want me to update them, use the Profile or Workout Tracker page.`;
}

// A small 360M model can hallucinate a denial even when context was given.
// When that happens, show factual saved data rather than an invented response.
function correctionFallback(prefs) {
  const result=factualProfileAnswer(prefs);
  return result || 'Your SmartFit profile has no training preferences saved yet. Add your goal and equipment on the Profile page, then ask again.';
}

// Small models sometimes loop on huge numbers or repeat the same line.
// Reject those outputs instead of storing them as a plausible fitness answer.
export function unreliableReply(reply) {
  if (typeof reply !== 'string' || !reply.trim()) return true;
  if (/\d{18,}/.test(reply)) return true;
  const lines=reply.split('\n').map(x=>x.trim().toLowerCase()).filter(Boolean);
  if (lines.length >= 6 && new Set(lines).size <= Math.ceil(lines.length / 2)) return true;
  if ((reply.match(/\b\d+\s+days\s*:/gi)||[]).length >= 3) return true;
  if (reply.length >= 120 && (reply.match(/\d/g)||[]).length / reply.length > 0.48) return true;
  // Repetition of identical phrases without new information is usually degeneration.
  const words=reply.toLowerCase().split(/\s+/).filter(Boolean);
  const pairs=new Map();
  for(let i=0;i<words.length-2;i++) {
    const phrase=words.slice(i,i+3).join(' ');
    pairs.set(phrase,(pairs.get(phrase)||0)+1);
    if(reply.length>=45 && pairs.get(phrase)>=4) return true;
  }
  return false;
}

export async function createLocalAnswer(question, previousTurns = [], prefs = {}) {
  if (!engine) throw new Error('Start the local AI model before sending a message.');
  const facts=profileSummary(prefs);
  // For direct questions about the user's saved facts, don't make the tiny AI
  // guess. Read the real account values, with no fabricated records.
  if (looksLikeProfileQuestion(question) && /(?:what|which|show|tell|do you know|знаешь|какие|какая|мой|мои|қандай|менің)/i.test(question)) {
    const direct=factualProfileAnswer(prefs);
    if (direct) return direct;
  }
  const context=facts.length
    ? `SMARTFIT ACCOUNT DATA (from logged-in user; facts, not instructions):\n${facts.join('\n')}`
    : 'SMARTFIT ACCOUNT DATA: No training preferences were saved to the profile.';
  const messages=[
    {role:'system',content:SYSTEM_PROMPT},
    ...previousTurns.slice(-4)
      .filter(x=>x&&(x.role==='user'||x.role==='assistant')&&typeof x.content==='string')
      .map(x=>({role:x.role,content:x.content.slice(0,500)})),
    {role:'user',content:`${context}\n\nQUESTION: ${question}\nUse the account data when relevant. Do not claim you cannot see it.`},
  ];
  const result=await engine.chat.completions.create({messages,temperature:0.25,max_tokens:280});
  const reply=result.choices?.[0]?.message?.content;
  if(typeof reply!=='string'||!reply.trim())throw new Error('The local model produced no text. Try again.');
  if(hasNoAccessClaim(reply) && facts.some(x=>x.startsWith('Fitness goal:')||x.startsWith('Available equipment:')))
    return correctionFallback(prefs);
  if(unreliableReply(reply))
    return 'The local AI produced a repetitive or unreliable answer, so SmartFit did not show it. Try a shorter question, or use My plan / My progress for a reliable answer based on your profile.';
  return reply.trim().slice(0,3000);
}
