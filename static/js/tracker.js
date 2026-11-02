/* Workout tracker: progressive enhancement for multi-exercise forms. */
(() => {
  'use strict';
  const template = document.getElementById('tp-exercise-template');
  if (!template) return;
  document.querySelectorAll('.tp-workout-form').forEach(form => {
    const list = form.querySelector('[data-exercise-list]');
    const add = form.querySelector('[data-add-exercise]');
    if (!list || !add) return;
    function updateControls() {
      const total=list.querySelectorAll('.tp-exercise-row').length;
      add.disabled=total>=12;
      list.querySelectorAll('[data-remove-exercise]').forEach(btn => {btn.disabled=total<=1;});
    }
    add.addEventListener('click', () => {
      if (list.querySelectorAll('.tp-exercise-row').length>=12) return;
      list.appendChild(template.content.cloneNode(true));
      updateControls();
      list.lastElementChild?.querySelector('input[name="exercise"]')?.focus();
    });
    list.addEventListener('click', event => {
      const btn=event.target.closest('[data-remove-exercise]');
      if (!btn || list.querySelectorAll('.tp-exercise-row').length<=1) return;
      btn.closest('.tp-exercise-row')?.remove();
      updateControls();
    });
    updateControls();
  });
})();
