/* SmartFit Free Food Scanner — on-device browser inference, no API key. */
const fileInput = document.querySelector('#food-photo');
const button = document.querySelector('#scan-food');
const status = document.querySelector('#food-status');
const results = document.querySelector('#food-results');
const preview = document.querySelector('#food-preview');
const previewImg = document.querySelector('#food-preview-img');
let photoUrl = null;
let classifierPromise = null;
const setStatus = (message) => { status.textContent = message; };
const cleanLabel = (name) => name.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
const escapeHtml = (s) => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function resetPreview() {
  if (photoUrl) URL.revokeObjectURL(photoUrl);
  photoUrl = null;
  results.hidden = true;
  results.replaceChildren();
}
fileInput.addEventListener('change', () => {
  resetPreview();
  const file = fileInput.files?.[0];
  if (!file) { preview.hidden = true; setStatus('Choose a photo to begin.'); return; }
  if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size > 3_000_000) {
    fileInput.value = ''; preview.hidden = true;
    setStatus('Choose a JPG, PNG or WebP photo smaller than 3 MB.'); return;
  }
  photoUrl = URL.createObjectURL(file);
  previewImg.src = photoUrl;
  preview.hidden = false;
  setStatus('Ready to identify food. Your photo stays in this browser.');
});
button.addEventListener('click', async () => {
  const file = fileInput.files?.[0];
  if (!file || !photoUrl) { setStatus('Choose a photo first.'); return; }
  button.disabled = true;
  results.hidden = true;
  try {
    setStatus('Loading free food recognition model (first time may download ~93 MB)…');
    if (!classifierPromise) {
      classifierPromise = import('https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1')
        .then(({pipeline, env}) => {
          env.allowLocalModels = false;
          return pipeline('image-classification', 'onnx-community/swin-finetuned-food101-ONNX', {device:'wasm', dtype:'q8'});
        })
        .catch(err => { classifierPromise = null; throw err; });
    }
    const classifier = await classifierPromise;
    setStatus('Identifying the dish on your device…');
    const predictions = await classifier(photoUrl, {top_k:3});
    const list = Array.isArray(predictions) ? predictions : [predictions];
    results.innerHTML = '<h2>Possible dishes</h2><ol>' + list.map(p =>
      '<li><strong>' + escapeHtml(cleanLabel(String(p.label))) + '</strong> <span>' +
      Math.round(Number(p.score)*100) + '% model confidence</span></li>'
    ).join('') + '</ol><p>This model recognizes 101 dish types, not individual ingredients or portion sizes. Its suggestions may be incorrect, especially for mixed or regional dishes. A photo cannot reliably calculate calories, protein, fats or carbohydrates. Verify ingredients and consult food packaging or an established food database for nutrition information.</p>';
    results.hidden = false;
    setStatus('Analysis complete. No photo was uploaded to the SmartFit server.');
  } catch (err) {
    console.error('Food scanner error:', err);
    setStatus('The free model could not load or run. Check your internet connection and try again in a modern desktop browser. Large model downloads or browser memory limits can cause failures.');
  } finally {
    button.disabled = false;
  }
});
window.addEventListener('pagehide', resetPreview);
